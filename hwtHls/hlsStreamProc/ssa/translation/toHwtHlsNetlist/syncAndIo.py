from typing import Tuple, Union, List, Set, Dict, Type

from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.unit import Unit
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.hlsStreamProc.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.branchControlLabel import BranchControlLabel
from hwtHls.netlist.nodes.io import HlsWrite, HlsRead
from hwtHls.netlist.nodes.ports import HlsOperationOut, link_hls_nodes, \
    HlsOperationOutLazy
from hwtHls.tmpVariable import HlsTmpVariable
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from ipCorePackager.constants import INTF_DIRECTION
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.nodes.backwardEdge import HlsWriteBackwardEdge, \
    HlsReadBackwardEdge


class SsaToHwtHlsNetlistSyncAndIo():
    """
    This object exists so :class:`hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.SsaToHwtHlsNetlist`
    does not need to care about differnces between local data and data from ports which were constructed
    to avoid circuit cycles for scheduler.
    """

    def __init__(self, parent: "SsaToHwtHlsNetlist",
                 out_of_pipeline_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]],
                 edge_var_live: EdgeLivenessDict):
        self.hls: HlsPipeline = parent.hls
        self.inputs: List[HlsRead] = parent.hls.inputs
        self.outputs: List[HlsWrite] = parent.hls.outputs
        self.parent = parent
        self.out_of_pipeline_edges = out_of_pipeline_edges
        self.out_of_pipeline_edges_sorted = sorted(out_of_pipeline_edges, key=lambda x: (x[0].label, x[1].label))
        self.out_of_pipeline_edges_ports: List[Tuple[HlsRead, HlsWrite], Tuple[SsaBasicBlock, SsaBasicBlock]] = []
        # a list of unique interfaces which connects this hls component to outside word and which needs to be coherency checked
        self._out_of_hls_io: UniqList[Interface] = UniqList()
        self._out_of_hls_variable_value_in: Dict[Tuple[HlsTmpVariable, SsaBasicBlock],
                                                 Union[HlsOperationOut, HlsOperationOutLazy]] = {}
        self._out_of_hls_variable_value_out: Dict[Tuple[HlsTmpVariable, SsaBasicBlock],
                                                  Union[HlsOperationOut, HlsOperationOutLazy]] = {}

        self.edge_var_live = edge_var_live

    def init_out_of_hls_variables(self):
        """
        Initialize all input interfaces for every input variables and control.
        """
        if not self.parent.start_block.predecessors:
            self.parent.start_block_en = start_in = HsStructIntf()
            start_in.T = BIT
            self._add_intf_instance(start_in, f"{self.parent.start_block.label}_start")
            self.parent.start_block_en_r = self._read_from_io(start_in)

        # After we split the SsaBasicBlocks to pipeline we marked some edges to be outside of pipeline
        # this means that these paths are associated with a variables which do corresponds to variable from SSA
        # but we need to represent them with a channel(s) and memories.
        # In default we need to construct the in/out channels for each block edge for data and controll.
        # In a pipeline the multiple values for a single value may appear.
        # Because of this we need to pay an extra care to origin of the variable value.
        # The variable value may come from an implicit mux betwen blocks, from multiple input channels corresponding
        # to a different block or from a write performed by some block in pipeline.
        # From this reason we need to know which value value is used on the beginning and the end of the block.
        for (src_block, dst_block) in self.out_of_pipeline_edges_sorted:
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
            # (10, x, x -1) this block must wait only on the input specified by controll
            # otherwise the circuit would deadlock because other values were not produced and thus they are not available

            # Each block which which has successors provides a flag for each successor which marks
            # if that branch was selected
            # The block can not finish its work until it receives this token from each predecessor.
            # By default the token format is a simple 1 bit where 1 means the branch was taken.
            # In out-of-order/speculative mode the token have format of tuple of ids and validity flags.
            src_block: SsaBasicBlock
            dst_block: SsaBasicBlock
            op_cache = self.parent._to_hls_cache
            _, r_from_in = self._add_hs_intf_and_read(
                f"c_{src_block.label:s}_to_{dst_block.label:s}_in", BIT, HlsReadBackwardEdge)
            label = BranchControlLabel(src_block, dst_block, INTF_DIRECTION.SLAVE)
            op_cache.add(label, r_from_in)
            self.out_of_pipeline_edges_ports.append(
                ([r_from_in.obj, None], (src_block, dst_block)))

            out_of_pipeline_vars = self.edge_var_live.get(src_block, {}).get(dst_block, ())
            for opv in sorted(out_of_pipeline_vars, key=lambda x: x.name):
                opv: HlsTmpVariable
                # The input interface is required for every input which is not just passing data
                # inside of pipeline this involves backward edges and external IO
                _, from_in = self._add_hs_intf_and_read(f"{opv._name:s}_in", opv._dtype, HlsReadBackwardEdge)
                op_cache.add((dst_block, opv), from_in)
                self._out_of_hls_variable_value_in[(opv, dst_block)] = from_in

                # HlsWrite set to None because write port will be addet later
                self.out_of_pipeline_edges_ports.append(([from_in.obj, None],
                                                         (src_block, dst_block)))

    def finalize_out_of_pipeline_variable_outputs(self):
        assert self.parent._current_block is None
        # the ports are generated by init_out_of_hls_variables and should be in same order
        # as this cycle iterates
        ports_it = iter(self.out_of_pipeline_edges_ports)
        for (src_block, dst_block) in self.out_of_pipeline_edges_sorted:
            out_of_pipeline_vars = self.edge_var_live.get(src_block, {}).get(dst_block, ())
            self.parent._current_block = src_block
            control_ext_ports = next(ports_it)

            cache_key = BranchControlLabel(src_block, dst_block, INTF_DIRECTION.MASTER)
            end_val = self.parent._to_hls_cache.get(cache_key)
            end_val = self.parent.to_hls_expr(end_val)
            assert isinstance(end_val, HlsOperationOut), (end_val, "Must be already existing output")
            # w_to_out = self._add_to_to_hls_cache(cache_key, end_val)
            _, w_to_out = self._add_hs_intf_and_write(f"c_{src_block.label:s}_to_{dst_block.label:s}_out", BIT, end_val, HlsWriteBackwardEdge)
            w_to_out.associate_read(control_ext_ports[0][0])
            control_ext_ports[0][1] = w_to_out

            for opv in sorted(out_of_pipeline_vars, key=lambda x: x.name):
                opv: HlsTmpVariable
                # take the value of variable on the end and write it to a newly generated port
                _, w_to_out = self._add_hs_intf_and_write(f"{opv._name:s}_out", opv._dtype, self.parent.to_hls_expr(opv), HlsWriteBackwardEdge)
                var_ext_ports = next(ports_it)
                w_to_out.associate_read(var_ext_ports[0][0])
                var_ext_ports[0][1] = w_to_out

            self.parent._current_block = None

        for k, v in self.parent._block_ens.items():
            assert not isinstance(v, HlsOperationOutLazy) or v.replaced_by, ("All outputs should be already resolved", k, v)

        for k, v in self.parent._to_hls_cache.items():
            assert not isinstance(v, HlsOperationOutLazy), ("All outputs should be already resolved", k, v)

    def _add_hs_intf_and_write(self, suggested_name: str, dtype:HdlType,
                               val: Union[HlsOperationOut, HlsOperationOutLazy],
                               write_cls:Type[HlsWrite]=HlsWrite):
        intf = HsStructIntf()
        intf.T = dtype
        self._add_intf_instance(intf, suggested_name)
        return intf, self._write_to_io(intf, val, write_cls=write_cls)

    def _add_hs_intf_and_read(self, suggested_name: str, dtype:HdlType, read_cls:Type[HlsRead]=HlsRead):
        intf = HsStructIntf()
        intf.T = dtype
        return intf, self._add_intf_and_read(intf, suggested_name, read_cls=read_cls)

    def _add_intf_and_read(self, intf: Interface, suggested_name: str, read_cls:Type[HlsRead]=HlsRead) -> Interface:
        self._add_intf_instance(intf, suggested_name)
        return self._read_from_io(intf, read_cls=read_cls)

    def _add_intf_instance(self, intf: Interface, suggested_name: str) -> Interface:
        """
        Sport interface instance in parent unit.
        """
        u:Unit = self.hls.parentUnit
        name = AbstractComponentBuilder(u, None, "hls")._findSuitableName(suggested_name)
        setattr(u, name, intf)
        self.hls._io[intf] = intf
        return intf

    def _construct_io_pair(self, name:str, t: HdlType,
                           src_out_port: Union[HlsOperationOut, HlsOperationOutLazy]) -> Tuple[HlsWrite, HlsOperationOut]:
        in_var = HsStructIntf()
        out_var = HsStructIntf()
        out_var.T = in_var.T = t

        self._add_intf_instance(out_var, f"{name:s}_out")
        w_to_out = self._write_to_io(out_var, src_out_port, HlsWriteBackwardEdge)

        self._add_intf_instance(in_var, f"{name:s}_in")
        from_in = self._read_from_io(in_var, HlsReadBackwardEdge)
        w_to_out.associate_read(from_in)

        return w_to_out, from_in

    def _write_to_io(self, intf: Interface,
                     val: Union[HlsOperationOut, HlsOperationOutLazy],
                     write_cls:Type[HlsWrite]=HlsWrite) -> HlsWrite:
        """
        Instanciate HlsWrite operation for this specific interface.
        """
        write = write_cls(self.hls, val, intf)
        if self.parent._current_block is not None:
            self.parent._add_block_en_to_controll_if_required(write)

        self.hls._io[intf] = intf
        link_hls_nodes(val, write._inputs[0])
        self.outputs.append(write)
        # self.nodes.append(write)
        return write

    def _read_from_io(self, intf: Interface, read_cls:Type[HlsRead]=HlsRead) -> HlsOperationOut:
        """
        Instantiate HlsRead operation for this specific interface.
        """
        read = read_cls(self.hls, intf)
        if self.parent._current_block is not None and intf is not self.parent.start_block_en:
            self.parent._add_block_en_to_controll_if_required(read)
        self.inputs.append(read)
        # self.nodes.append(read)

        return read._outputs[0]

    # def _write_to_out_of_pipeline_variable(self,
    #                                       opv: HlsTmpVariable,
    #                                       src: Union[HlsOperationOut, HlsOperationOutLazy]):
    #    # create an interface for a variable which is corssing boundary
    #    out_var = HsStructIntf()
    #    out_var.T = opv._dtype
    #
    #    self._io._add_intf_instance(out_var, f"{opv._name:s}_out")
    #    src_write = self._io._write_to_io(out_var, src)
    #    self.out_of_pipeline_edges_ports.append((
    #        (src_write, self._to_hls_cache[opv].obj),
    #        self._out_of_hls_variables[opv]
    #    ))
    #    # [TODO] from now the varialbe has this specified value and the previous value should not be used
    #    #        however the blocks may not be entirely linearized and we may actually use wrong value
    #    #        if we did not process all places which were using the old value
    #    self._to_hls_cache[opv] = src

