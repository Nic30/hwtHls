from typing import Tuple, Union, List, Set, Type, Optional, Dict

from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.unit import Unit
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.netlist.nodes.io import HlsNetNodeWrite, HlsNetNodeRead
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, \
    HlsNetNodeOutLazy
from hwtHls.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.branchControlLabel import BranchControlLabel
from hwtHls.ssa.translation.toHwtHlsNetlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge, \
    HlsNetNodeReadBackwardEdge
from hwtHls.ssa.translation.toHwtHlsNetlist.nodes.programStarter import HlsProgramStarter
from hwtHls.ssa.value import SsaValue
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from ipCorePackager.constants import INTF_DIRECTION


class BlockPortsRecord():

    def __init__(self, has_control, port_list:List[Tuple[HlsNetNodeReadBackwardEdge, Tuple[SsaBasicBlock, SsaBasicBlock]]]):
        self.has_control = has_control
        self.port_list = port_list


class SsaToHwtHlsNetlistSyncAndIo():
    """
    This object exists so :class:`hwtHls.ssa.translation.toHwtHlsNetlist.SsaToHwtHlsNetlist`
    does not need to care about differnces between local data and data from ports which were constructed
    to avoid circuit cycles for scheduler.


    :ivar start_block_en: optionaly port to trigger the program execution
    """

    def __init__(self, parent: "SsaToHwtHlsNetlist",
                 out_of_pipeline_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]],
                 edge_var_live: EdgeLivenessDict):
        self.hls: HlsPipeline = parent.hls
        self.parent = parent
        self.inputs: List[HlsNetNodeRead] = parent.hls.inputs
        self.outputs: List[HlsNetNodeWrite] = parent.hls.outputs
        self.out_of_pipeline_edges = out_of_pipeline_edges
        # a list of unique interfaces which connects this hls component to outside word and which needs to be coherency checked
        self._out_of_hls_io: UniqList[Interface] = UniqList()

        self._block_io: Dict[Tuple[SsaBasicBlock, SsaBasicBlock], BlockPortsRecord] = {}
        self.edge_var_live = edge_var_live
        self.start_block_en: Optional[HlsNetNodeOut] = None

    def _add_HlsProgramStarter(self):
        """
        Add a node which provides a starting sync token for the start block after reset.
        """
        # can not be synchronized by data we need an explicit synchronisation node
        sync_node = HlsProgramStarter(self.hls)
        self.hls.nodes.append(sync_node)
        self.start_block_en = sync_node._outputs[0]

    def init_out_of_pipeline_variables(self,
            src_block: SsaBasicBlock, dst_block: SsaBasicBlock,
            add_control:bool) -> List[Tuple[HlsNetNodeReadBackwardEdge, Tuple[SsaBasicBlock, SsaBasicBlock]]]:
        """
        Initialize all input interfaces for every input variables and control.

        :note: Needs to be done in dst_block because we need the synchronisation for the input.
        """
        # After we split the SsaBasicBlocks to pipeline we marked some edges to be outside of pipeline
        # this means that these paths are associated with a variables which do corresponds to variable from SSA
        # but we need to represent them with a channel(s) and memories.

        # In default we need to construct the in/out channels for each block edge for data and control.
        # In a pipeline the multiple values for a single value may appear.
        # Because of this we need to pay an extra care to origin of the variable value.
        # The variable value may come from an implicit mux betwen blocks, from multiple input channels corresponding
        # to a different block or from a write performed by some block in pipeline.
        # From this reason we need to know which value value is used on the beginning and the end of the block.

        # all consumers of a variable must take it from a same source
        # the variable is always writen on a single place in code,
        # however for example due multiple breaks in a loop the veriable may have multiple
        # paths how to get out of pipeline and also inside. This case has to be explicitely handled.
        # In addition each variable alive on out of pipeline edge:
        #  * must have a single input interface
        #    * such a variables are because of cycle
        #      cycle may be entered only at te beginning (because of structural programing)
        #  * must have a single output interface
        #    * becaues by SSA def var. may be written only once
        #    * this implies that input must not wait on output if the input is not required
        #    * output must wait until it is confirmed to prevent
        #  * :attention: the variable uses which preceeds the definition of variable in pipeline
        #    (such places do exists because we removed some edges whcih did assert that variable was defined first)
        #    must use the value from input, the places  after definition must use latest value of variable
        #    that means the value from definition or original value if the variable was not written on the way
        # for example in the code
        # .. code-block:: Python
        #     x = 10
        #     while True:
        #        if x == 3:
        #            continue
        #        x -= 1
        #
        # the while condition block has 3 different input variables (for orig. var "x")
        # (10, x, x -1) this block must wait only on the input specified by control
        # otherwise the circuit would deadlock because other values were not produced and thus they are not available

        # Each block which which has successors provides a flag for each successor which marks
        # if that branch was selected
        # The block can not finish its work until it receives this token from each predecessor.
        # By default the token format is a simple 1 bit where 1 means the branch was taken.
        # In out-of-order/speculative mode the token have format of tuple of ids and validity flags.
        op_cache = self.parent._to_hls_cache
        newly_added_ports = []
        if add_control:
            _, r_from_in = self._add_hs_intf_and_read(
                f"c_{src_block.label:s}_to_{dst_block.label:s}_in", BIT, HlsNetNodeReadBackwardEdge)
            label = BranchControlLabel(src_block, dst_block, INTF_DIRECTION.SLAVE)
            op_cache.add(label, r_from_in, False)
            newly_added_ports.append((r_from_in.obj, (src_block, dst_block)))

        out_of_pipeline_vars = self.edge_var_live.get(src_block, {}).get(dst_block, ())
        for opv in sorted(out_of_pipeline_vars, key=lambda x: x._name):
            opv: SsaValue
            # The input interface is required for every input which is not just passing data
            # inside of pipeline this involves backward edges and external IO
            _, from_in = self._add_hs_intf_and_read(f"{opv._name:s}_in", opv._dtype, HlsNetNodeReadBackwardEdge)
            op_cache.add((dst_block, opv), from_in, False)

            # HlsNetNodeWrite set to None because write port will be addet later
            newly_added_ports.append((from_in.obj, (src_block, dst_block)))

        assert (src_block, dst_block) not in self._block_io
        self._block_io[(src_block, dst_block)] = BlockPortsRecord(add_control, newly_added_ports)

    def finalize_block_out_of_pipeline_variable_outputs(self,
            src_block: SsaBasicBlock, dst_block: SsaBasicBlock):
        """
        :note: Needs to be done in src_block because we need the synchronization for the output.
        """
        assert self.parent._current_block is src_block
        block_ports = self._block_io[(src_block, dst_block)]
        # the ports are generated by init_out_of_hls_variables and should be in same order
        # as this cycle iterates
        ports_it = iter(block_ports.port_list)

        control_cache_key = BranchControlLabel(src_block, dst_block, INTF_DIRECTION.MASTER)
        if block_ports.has_control:
            control_ext_ports = next(ports_it)
            end_val = self.parent._to_hls_cache.get(control_cache_key)
            end_val = self.parent.to_hls_expr(end_val)
            assert isinstance(end_val, HlsNetNodeOut), ("Must be already existing output", control_cache_key, end_val)
            # w_to_out = self._add_to_to_hls_cache(cache_key, end_val)
            _, w_to_out = self._add_hs_intf_and_write(f"c_{src_block.label:s}_to_{dst_block.label:s}_out", BIT,
                                                      end_val, HlsNetNodeWriteBackwardEdge)
            w_to_out.associate_read(control_ext_ports[0])
        else:
            assert control_cache_key not in self.parent._to_hls_cache._to_hls_cache, "The control must not be used anywhere if it should not exists."

        out_of_pipeline_vars = self.edge_var_live.get(src_block, {}).get(dst_block, ())
        for opv in sorted(out_of_pipeline_vars, key=lambda x: x._name):
            opv: SsaValue
            # take the value of variable on the end and write it to a newly generated port
            _, w_to_out = self._add_hs_intf_and_write(f"{opv._name:s}_out", opv._dtype,
                                                      self.parent.to_hls_expr(opv), HlsNetNodeWriteBackwardEdge)
            var_ext_ports = next(ports_it)
            w_to_out.associate_read(var_ext_ports[0])

    def _add_hs_intf_and_write(self, suggested_name: str, dtype:HdlType,
                               val: Union[HlsNetNodeOut, HlsNetNodeOutLazy],
                               write_cls:Type[HlsNetNodeWrite]=HlsNetNodeWrite):
        intf = HsStructIntf()
        intf.T = dtype
        self._add_intf_instance(intf, suggested_name)
        return intf, self._write_to_io(intf, val, write_cls=write_cls)

    def _add_hs_intf_and_read(self, suggested_name: str, dtype:HdlType, read_cls:Type[HlsNetNodeRead]=HlsNetNodeRead):
        intf = HsStructIntf()
        intf.T = dtype
        return intf, self._add_intf_and_read(intf, suggested_name, read_cls=read_cls)

    def _add_intf_and_read(self, intf: Interface, suggested_name: str, read_cls:Type[HlsNetNodeRead]=HlsNetNodeRead) -> Interface:
        self._add_intf_instance(intf, suggested_name)
        return self._read_from_io(intf, read_cls=read_cls)

    def _add_intf_instance(self, intf: Interface, suggested_name: str) -> Interface:
        """
        Spot interface instance in parent unit.
        """
        u:Unit = self.hls.parentUnit
        name = AbstractComponentBuilder(u, None, "hls")._findSuitableName(suggested_name)
        setattr(u, name, intf)
        return intf

    def _write_to_io(self, intf: Interface,
                     val: Union[HlsNetNodeOut, HlsNetNodeOutLazy],
                     write_cls:Type[HlsNetNodeWrite]=HlsNetNodeWrite) -> HlsNetNodeWrite:
        """
        Instanciate HlsNetNodeWrite operation for this specific interface.
        """
        write = write_cls(self.hls, val, intf)
        if self.parent._current_block is not None and intf in self._out_of_hls_io:
            self.parent._add_block_en_to_control_if_required(write)

        link_hls_nodes(val, write._inputs[0])
        self.outputs.append(write)

        return write

    def _read_from_io(self, intf: Interface, read_cls:Type[HlsNetNodeRead]=HlsNetNodeRead) -> HlsNetNodeOut:
        """
        Instantiate HlsNetNodeRead operation for this specific interface.
        """
        read = read_cls(self.hls, intf)
        if self.parent._current_block is not None and intf in self._out_of_hls_io:
            self.parent._add_block_en_to_control_if_required(read)
        self.inputs.append(read)

        return read._outputs[0]

