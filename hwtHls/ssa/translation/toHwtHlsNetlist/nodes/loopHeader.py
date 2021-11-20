from typing import List, Tuple, Optional, Union

from hwt.pyUtils.uniqList import UniqList
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.clk_math import epsilon
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.netlist.nodes.io import HlsExplicitSyncNode, IO_COMB_REALIZATION
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.netlist.nodes.ports import HlsOperationOut, link_hls_nodes, HlsOperationOutLazy
from hwtHls.netlist.utils import hls_op_not
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.branchControlLabel import BranchControlLabel
from hwtHls.ssa.translation.toHwtHlsNetlist.opCache import SsaToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.toHwtHlsNetlist.syncAndIo import SsaToHwtHlsNetlistSyncAndIo
from ipCorePackager.constants import INTF_DIRECTION


class HlsLoopGateStatus(AbstractHlsOp):

    def __init__(self, parentHls:"HlsPipeline", loop_gate: "HlsLoopGate", name:str=None):
        AbstractHlsOp.__init__(self, parentHls, name=name)
        self._loop_gate = loop_gate
        self._add_output()

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        op_out = self._outputs[0]

        try:
            return allocator.node2instance[op_out]
        except KeyError:
            pass

        name = self.name
        status_reg = allocator._reg(name if name else "loop_gate_status", def_val=0)
        # [todo] set this register based on how data flows on control channels
        # (breaks returns token, predec takes token)

        # create RTL signal expression base on operator type
        t = self.scheduledInEnd[0] + epsilon
        status_reg_s = TimeIndependentRtlResource(status_reg, t, allocator)
        allocator._registerSignal(op_out, status_reg_s, used_signals)
        return status_reg_s


class HlsLoopGate(AbstractHlsOp):
    """
    This operation represents a start of a loop, not all loops necessary need this.
    This operation tells the allocator that the start_inputs after the processing
    of previous data has finished.
    Depending on hw realization this may be solved combinationaly or with the tagging etc.

    In basic configuration this operation waits for all input on start_inputs,
    once provided the data is passed to outputs, until there is data from cycle which marks for
    end of the loop the next data from start_inputs is not taken and end_inputs are used instead.

    :note: This is a special operation and not just mux because it has potentially multiple inputs and outputs
        from some of them may be enabled conditionally.


    There are several modes of operation:
    * non-speculative, blocking - new start of cycle may happen only after the data from previous iterration are availabe
        * requires a special flag to detect the state when there is no loop running to avoid wait for data crom previous iterration

        .. code-block:: Python

            i = 1
            while i:
                i = input.read()


    * non-blocking, speculative - every data transaction have tag assigned on the input, new data can always enter the loop
       (if back pressure allows it) the loop iterration is always speculative until previous iteration confirms it
       (or the circuit was idle and this is first transaction in loop body)
        * this is possible if there is no data dependency or if data value can be predicted/precomputed/forwarded (including induction variable)

        .. code-block:: Python

            i = 1
            while True:
                i += input.read()


    :note: This object does not handle the condition decission, it only manages guards the loop input while loop iterations are running.
    :note: The place where this node bellong is characterized by a control input from the pipeline and also out of pipeline.
        The inputs from pipeline are from_predec and the inputs from out of pipeline are from_reenter.
    :note: to_loop are same outputs as from_predec + from_reenter, the only difference is that the order of input is managed and invalid values
        are send on the channel which is not active (and should not be actively used in the pipeline by control channel functionality).
    :ivar from_predec: for each direct predecessor which is not in cycle body a tuple input for control and variable values.
        Signalizes that the loop has data to be executed.
    :ivar from_reenter: For each direct predecessor which is a part of a cycle body a tuple control input and associated variables.
        Note that the channels are usually connected to out of pipeline interface because the HlsPipeline does not support cycles.
    :ivar from_break: For each block wich is part of the cycle body and does have transition outside of the cycle a control input
        to mark the retun of the synchronization token.
    :ivar to_loop: The control and variable channels which are entering the loop condition eval.
    :ivar to_successors: For each direct successor which is not the entry point of the loop body (because of structural programming there can be only one)
        a tuple of control and variable outputs.

    :note: values from from_predec are propagated to to_loop
    :note: if this gate has synchronization token it accepts only data from the from_predec then it accepts only from from_reenter/from_break
    """

    def __init__(self, parentHls:HlsPipeline,
            name:Optional[str]=None):
        AbstractHlsOp.__init__(self, parentHls, name=name)
        self.from_predec: List[HlsOperationOut] = []
        self.from_reenter: List[HlsOperationOut] = []
        self.from_break: List[HlsOperationOut] = []
        self.to_loop: List[HlsOperationOut] = []
        # another node with the output representing the presence of sync token (we can not add it here
        # because it would create a cycle)
        self._sync_token_status = HlsLoopGateStatus(parentHls, self)

    @classmethod
    def inset_before_block(cls, hls: HlsPipeline, block: SsaBasicBlock,
                           io: SsaToHwtHlsNetlistSyncAndIo,
                           to_hls_cache: SsaToHwtHlsNetlistOpCache,
                           nodes: List[AbstractHlsOp],
                           ):
        self = cls(hls, block.label)
        # Mark all inputs from predec as not required and stalled while we do not have sync token ready.
        # Mark all inputs from reenter as not required and stalled while we have a sync token ready.
        nodes.append(self._sync_token_status)
        for pred in block.predecessors:
            is_reenter = (pred, block) in io.out_of_pipeline_edges
            en = self._sync_token_status._outputs[0]
            if is_reenter:
                # en if has sync token
                pass
            else:
                # en if has no sync token
                en = hls_op_not(hls, en)
            control_key = BranchControlLabel(pred, block, INTF_DIRECTION.SLAVE)
            control = to_hls_cache.get(control_key)
            esn, control = HlsExplicitSyncNode.replace_variable(hls, control_key, control, to_hls_cache, en)
            nodes.append(esn)

            #variables = []
            for v in io.edge_var_live.get(pred, {}).get(block, ()):
                cache_key = (block, v)
                v = to_hls_cache.get(cache_key)
                esn, _ = HlsExplicitSyncNode.replace_variable(hls, cache_key, v, to_hls_cache, en)
                nodes.append(esn)
                #variables.append(v)

            if is_reenter:
                self.connect_reenter(control)
            else:
                self.connect_predec(control)

    def _connect(self, control:HlsOperationOut, in_list):
        in_list.append(control)
        i = self._add_input()
        link_hls_nodes(control, i)
        if isinstance(control, HlsOperationOutLazy):
            control.dependent_inputs.append(HlsLoopGateInputRef(self, in_list,
                                                                len(in_list) - 1, control))

    def connect_predec(self, control:HlsOperationOut):
        """
        Register connection of control and data from some block which causes the loop to to execute.
        :note: allocating the sync token
        """
        self._connect(control, self.from_predec)

    def connect_reenter(self, control:HlsOperationOut):
        """
        Register connection of control and data from some block where controlflow gets back block where the cycle starts.
        :note: reusing sync token
        """
        self._connect(control, self.from_reenter)

    def connect_break(self, control: HlsOperationOut):
        """
        Register connection of control which causes to break current execution of the loop.
        :note: deallocating the sync token
        :note: the loop may not end this implies that this may not be used at all
        """
        raise NotImplementedError()


class HlsLoopGateInputRef():
    """
    An object which is used in HlsOperationOutLazy dependencies to update also HlsLoopGate object
    once the lazy output of some node on input is resolved.

    :note: This is an additional input storage dependency. The input in dependsOn should be replaced separately.

    :ivar parent: an object where the we want to replace output connected to some of its input
    :ivar in_list: an list where is the input (HlsOperationOut object) stored additionally
    :ivar in_list_i: an index in in_list
    :ivar obj: an output object which was supposed to be on referenced place
    """

    def __init__(self, parent: HlsLoopGate, in_list: List[Union[HlsOperationOut, Tuple[HlsOperationOut, ...]]], in_list_i: int,
                 obj: HlsOperationOutLazy):
        self.parent = parent
        self.in_list = in_list
        self.in_list_i = in_list_i
        self.obj = obj
        assert self.in_list[self.in_list_i] is self.obj

    def replace_driver(self, new_obj: HlsOperationOut):
        assert self.in_list[self.in_list_i] is self.obj
        self.in_list[self.in_list_i] = new_obj
