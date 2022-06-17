from typing import List, Optional, Generator

from hwt.code import If, Or
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import IO_COMB_REALIZATION, HlsNetNodeReadSync, \
    HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, HlsNetNodeIn
from hwtHls.netlist.utils import hls_op_and, hls_op_not
from hwtHls.netlist.scheduler.clk_math import start_of_next_clk_period


class HlsLoopGateStatus(HlsNetNode):
    """
    The status of HlsLoopGate which holds a register with a state of execution of the loop.
    It specifies if the loop is currently running or if it can be executed.
    
    :ivar _loop_gate: parent loop gate which is using this status (this is a separate object to simplify scheduling dependencies)
    """

    def __init__(self, netlist:"HlsNetlistCtx", loop_gate: "HlsLoopGate", name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
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
        g = self._loop_gate
        statusBusyReg = allocator._reg(
            name if name else "loop_gate_busy",
            def_val=0 if g.from_predec else 1)  # busy if is executed at 0 time

        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + self.netlist.scheduler.epsilon
        statusBusyReg_s = TimeIndependentRtlResource(statusBusyReg, t, allocator)
        allocator.netNodeToRtl[op_out] = statusBusyReg_s

        # returns the control token
        from_break = [allocator.instantiateHlsNetNodeOut(g.dependsOn[i.in_i]) for i in g.from_break]
        # takes the control token
        from_predec = [allocator.instantiateHlsNetNodeOut(g.dependsOn[i.in_i]) for i in g.from_predec]
        # has the priority and does not require sync token (because it already owns it)
        from_reenter = [allocator.instantiateHlsNetNodeOut(g.dependsOn[i.in_i]) for i in g.from_reenter]

        assert from_reenter, (g, "Must have some reenters otherwise this is not the loop")
        if not from_break and not from_predec:
            # this is infinite loop without predecessor, it will run infinitely but in just one instance
            statusBusyReg(1)
        elif not from_break and from_predec:
            # this is an infinite loop which has a predecessor, once started it will be closed for new starts
            # :attention: we pick the data from any time because this is kind of back edge
            newExe = Or(*(p.get(p.timeOffset).data for p in from_predec))
            If(newExe,
               statusBusyReg(1)
            )
        elif from_break and from_predec:
            newExe = Or(*(p.get(p.timeOffset).data for p in from_predec))
            newExit = Or(*(p.get(p.timeOffset).data for p in from_break))
            If(newExe & ~newExit,
               statusBusyReg(1)  # becomes busy
            ).Elif(~newExe & newExit,
               statusBusyReg(0)  # finished work
            )
        elif from_break and not from_predec:
            newExit = Or(*(p.get(p.timeOffset).data for p in from_break))
            If(newExit,
               statusBusyReg(0)  # finished work
            )
        else:
            raise AssertionError("All cases whould be covered in this if", self, g)

        return statusBusyReg_s

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"


class HlsLoopGate(HlsNetNode):
    """
    This operation represents a start of a loop, not all loops necessary need this.
    Depending on HW realization this may be solved combinationally or with the tagging etc.

    In basic configuration this operation waits for all input on start_inputs,
    once provided the data is passed to outputs, until there is data from cycle which marks for
    end of the loop the next data from start_inputs is not taken and end_inputs are used instead.

    :note: This does not contain any multiplexers or explicit synchronization it is just a state-full control logic.

    There are several modes of operation:
    * non-speculative, blocking - new start of cycle may happen only after the data from previous iteration are available
        * requires a special flag to detect the state when there is no loop running to avoid wait for data crom previous iteration

        .. code-block:: Python

            i = 1
            while i:
                i = input.read()


    * non-blocking, speculative - every data transaction have tag assigned on the input, new data can always enter the loop
       (if back pressure allows it) the loop iteration is always speculative until previous iteration confirms it
       (or the circuit was idle and this is first transaction in loop body)
        * this is possible if there is no data dependency or if data value can be predicted/precomputed/forwarded (including induction variable)

        .. code-block:: Python

            i = 1
            while True:
                i += input.read()


    :note: This object does not handle the condition decision, it only manages guards the loop input while loop iterations are running.
    :note: The place where this node belong is characterized by a control input from the pipeline and also out of pipeline.
        The inputs from pipeline are from_predec and the inputs from out of pipeline are from_reenter.
    
    :ivar from_predec: for each direct predecessor which is not in cycle body a tuple input for control and variable values.
        Signalizes that the loop has data to be executed.
    :ivar from_reenter: For each direct predecessor which is a part of a cycle body a tuple control input and associated variables.
        Note that the channels are usually connected to out of pipeline interface because the HlsNetlistCtx does not support cycles.
    :ivar from_break: For each block which is part of the cycle body and does have transition outside of the cycle a control input
        to mark the return of the synchronization token.
    :ivar to_successors: For each direct successor which is not the entry point of the loop body (because of structural programming there can be only one)
        a tuple of control and variable outputs.

    :note: if this gate has synchronization token it accepts only data from the from_predec and then it accepts only from from_reenter/from_break
    :note: from_predec, from_reenter are read at the beginning of a loop header block. Breaks are read at the end of exit block.
    
    :ivar _sync_token_status: The node with state for this object.
    """

    def __init__(self, netlist:"HlsNetlistCtx",
            name:Optional[str]=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self.from_predec: List[HlsNetNodeIn] = []
        self.from_reenter: List[HlsNetNodeIn] = []
        self.from_break: List[HlsNetNodeIn] = []
        # another node with the output representing the presence of sync token (we can not add it here
        # because it would create a cycle)
        self._sync_token_status = HlsLoopGateStatus(netlist, self)

    def _removeInput(self, i:int):
        raise NotImplementedError()

    def _connect(self, control:HlsNetNodeOut, in_list: List[HlsNetNodeIn]):
        i = self._add_input()
        link_hls_nodes(control, i)
        in_list.append(i)

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
        assert isinstance(control.obj, HlsNetNodeExplicitSync), control
        vld = HlsNetNodeReadSync(self.netlist)
        self.netlist.nodes.append(vld)
        link_hls_nodes(control.obj.dependsOn[0], vld._inputs[0])
        control.obj.add_control_skipWhen(hls_op_not(self.netlist, vld._outputs[0]))
        en = hls_op_and(self.netlist, control, vld._outputs[0])
        self._connect(en, self.from_break)

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        yield self._sync_token_status

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def scheduleAlapCompaction(self, asapSchedule:SchedulizationDict):
        normalizedClkPeriod: int = self.netlist.normalizedClkPeriod
        if self.scheduledIn is not None:
            return self.scheduledIn
        # if it is terminator move to end of clk period
        self.scheduledIn, self.scheduledOut = asapSchedule[self]
        assert not self.scheduledOut, self
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        self.scheduledIn = tuple(start_of_next_clk_period(t, normalizedClkPeriod) - ffdelay for t in self.scheduledIn)
        return self.scheduledIn

    def allocateRtlInstance(self, allocator:"AllocatorArchitecturalElement"):
        """
        All circuits generated from :class:`~.HlsLoopGateStatus`
        """
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"
