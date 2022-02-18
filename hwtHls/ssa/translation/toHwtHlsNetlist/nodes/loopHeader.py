from typing import List, Tuple, Optional, Union

from hwt.code import If, Or
from hwt.hdl.types.defs import BIT
from hwtHls.allocator.connectionsOfStage import SignalsOfStages
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import epsilon
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.netlist.nodes.io import HlsNetNodeExplicitSync, IO_COMB_REALIZATION
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, HlsNetNodeOutLazy
from hwtHls.netlist.utils import hls_op_not
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.branchControlLabel import BranchControlLabel
from hwtHls.ssa.translation.toHwtHlsNetlist.opCache import SsaToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.toHwtHlsNetlist.syncAndIo import SsaToHwtHlsNetlistSyncAndIo
from ipCorePackager.constants import INTF_DIRECTION


class HlsLoopGateStatus(HlsNetNode):

    def __init__(self, parentHls:"HlsPipeline", loop_gate: "HlsLoopGate", name:str=None):
        HlsNetNode.__init__(self, parentHls, name=name)
        self._loop_gate = loop_gate
        self._add_output(BIT)

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self, allocator: "AllocatorArchitecturalElement") -> TimeIndependentRtlResource:
        op_out = self._outputs[0]

        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass

        name = self.name
        status_reg = allocator._reg(name if name else "loop_gate_status", def_val=0)

        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + epsilon
        status_reg_s = TimeIndependentRtlResource(status_reg, t, allocator)
        allocator.netNodeToRtl[op_out] = status_reg_s

        # [todo] set this register based on how data flows on control channels
        # (breaks returns token, predec takes token)
        # returns the controll token
        from_break = [allocator.instantiateHlsNetNodeOut(i) for i in  self._loop_gate.from_break]
        # takes the control token
        from_predec = [allocator.instantiateHlsNetNodeOut(i) for i in self._loop_gate.from_predec]
        # has the priority and does not require sync token (because it already owns it)
        from_reenter = [allocator.instantiateHlsNetNodeOut(i) for i in self._loop_gate.from_reenter]

        if not from_break and not from_predec and from_reenter:
            # this is infinite loop without predecessor, it will run infinitely but in just one instance
            status_reg(1)
        elif not from_break and from_predec and from_reenter:
            # this is an infinite loop which has a predecessor, once started it will be closed for new starts
            If(Or(*(p.get(t).data for p in from_predec)),
               status_reg(1)
            )
        else:
            raise NotImplementedError()

        return status_reg_s


class HlsLoopGate(HlsNetNode):
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
        HlsNetNode.__init__(self, parentHls, name=name)
        self.from_predec: List[HlsNetNodeOut] = []
        self.from_reenter: List[HlsNetNodeOut] = []
        self.from_break: List[HlsNetNodeOut] = []
        self.to_loop: List[HlsNetNodeOut] = []
        # another node with the output representing the presence of sync token (we can not add it here
        # because it would create a cycle)
        self._sync_token_status = HlsLoopGateStatus(parentHls, self)

    @classmethod
    def inset_before_block(cls, toHls: "SsaToHwtHlsNetlist", block: SsaBasicBlock,
                           io: SsaToHwtHlsNetlistSyncAndIo,
                           to_hls_cache: SsaToHwtHlsNetlistOpCache,
                           nodes: List[HlsNetNode],
                           ):
        hls = toHls.hls
        self = cls(hls, block.label)
        # Mark all inputs from predec as not required and stalled while we do not have sync token ready.
        # Mark all inputs from reenter as not required and stalled while we have a sync token ready.
        nodes.append(self._sync_token_status)
        nodes.append(self)
        for pred in block.predecessors:
            is_reenter = (pred, block) in io.out_of_pipeline_edges
            en = self._sync_token_status._outputs[0]
            not_en = hls_op_not(hls, en)

            if is_reenter:
                # en if has sync token
                pass
            else:
                # en if has no sync token
                en, not_en = not_en, en

            if toHls._blockMeta[pred].needsControl:
                control_key = BranchControlLabel(pred, block, INTF_DIRECTION.SLAVE)
                control = to_hls_cache.get(control_key)
                _, control = HlsNetNodeExplicitSync.replace_variable(hls, control_key, control, to_hls_cache, en, not_en)
            else:
                control = None

            # variables = []
            for v in io.edge_var_live.get(pred, {}).get(block, ()):
                cache_key = (block, v)
                v = to_hls_cache.get(cache_key)
                _, _ = HlsNetNodeExplicitSync.replace_variable(hls, cache_key, v, to_hls_cache, en, not_en)
                # variables.append(v)

            if control is not None:
                if is_reenter:
                    self.connect_reenter(control)
                else:
                    self.connect_predec(control)
        self._finalizeConnnections()

    def _finalizeConnnections(self):
        pass
        # if self.from_predec:
        #    raise NotImplementedError()
        # if self.from_break:
        #    raise NotImplementedError()

        # allow to execute loop with just a single value from reenter
        # in_list = self.from_reenter
        # if len(in_list) > 1:
        #     for inp0_i, inp0 in enumerate(in_list):
        #         inp0: HlsNetNodeOut
        #         anyOtherValid = []
        #         for inp1 in in_list:
        #             if inp1 is inp0:
        #                 continue
        #
        #             vld = HlsNetNodeReadSync(self.hls)
        #             self.hls.nodes.append(vld)
        #             otherInSyncNode = inp1.obj
        #             assert isinstance(otherInSyncNode, HlsNetNodeExplicitSync), otherInSyncNode
        #             link_hls_nodes(otherInSyncNode.dependsOn[0], vld._inputs[0])
        #             anyOtherValid.append(vld._outputs[0])
        #
        #         inSyncNode: HlsNetNodeExplicitSync = inp0.obj
        #         assert isinstance(inSyncNode, HlsNetNodeExplicitSync), inSyncNode
        #
        #         # any other valid
        #         skipWhen = hls_op_and_variadic(self.hls, *anyOtherValid)
        #         inSyncNode.add_control_skipWhen(skipWhen)
        #         # all previous not valid
        #         if inp0_i > 0:
        #             extraCond = hls_op_and_variadic(self.hls,
        #                                             *[hls_op_not(self.hls, o)
        #                                               for o in anyOtherValid[:inp0_i]])
        #             inSyncNode.add_control_extraCond(extraCond)

    def _connect(self, control:HlsNetNodeOut, in_list: List[HlsNetNodeOut]):
        in_list.append(control)
        i = self._add_input()
        link_hls_nodes(control, i)
        if isinstance(control, HlsNetNodeOutLazy):
            control.dependent_inputs.append(HlsLoopGateInputRef(self, in_list,
                                                                len(in_list) - 1, control))

    def connect_predec(self, control:HlsNetNodeOut):
        """
        Register connection of control and data from some block which causes the loop to to execute.
        :note: allocating the sync token
        """
        self._connect(control, self.from_predec)

    def connect_reenter(self, control:HlsNetNodeOut):
        """
        Register connection of control and data from some block where controlflow gets back block where the cycle starts.
        :note: reusing sync token
        """
        self._connect(control, self.from_reenter)

    def connect_break(self, control: HlsNetNodeOut):
        """
        Register connection of control which causes to break current execution of the loop.
        :note: deallocating the sync token
        :note: the loop may not end this implies that this may not be used at all
        """
        raise NotImplementedError()

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self, allocator:"AllocatorArchitecturalElement"):
        pass


class HlsLoopGateInputRef():
    """
    An object which is used in HlsNetNodeOutLazy dependencies to update also HlsLoopGate object
    once the lazy output of some node on input is resolved.

    :note: This is an additional input storage dependency. The input in dependsOn should be replaced separately.

    :ivar parent: an object where the we want to replace output connected to some of its input
    :ivar in_list: an list where is the input (HlsNetNodeOut object) stored additionally
    :ivar in_list_i: an index in in_list
    :ivar obj: an output object which was supposed to be on referenced place
    """

    def __init__(self, parent: HlsLoopGate, in_list: List[Union[HlsNetNodeOut, Tuple[HlsNetNodeOut, ...]]], in_list_i: int,
                 obj: HlsNetNodeOutLazy):
        self.parent = parent
        self.in_list = in_list
        self.in_list_i = in_list_i
        self.obj = obj
        assert self.in_list[self.in_list_i] is self.obj

    def replace_driver(self, new_obj: HlsNetNodeOut):
        assert self.in_list[self.in_list_i] is self.obj
        self.in_list[self.in_list_i] = new_obj
