from typing import List, Optional, Generator

from hwt.code import If, Or
from hwt.code_utils import rename_signal
from hwt.hdl.types.defs import BIT
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode, OutputMinUseTimeGetter
from hwtHls.netlist.nodes.orderable import HlsNetNodeOrderable
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, HlsNetNodeIn


class HlsLoopGateStatus(HlsNetNode):
    """
    The status of HlsLoopGate which holds a register with a state of execution of the loop.
    It specifies if the loop is currently running or if it can be executed.
    
    :ivar _loop_gate: parent loop gate which is using this status (this is a separate object to simplify scheduling dependencies)
    """

    def __init__(self, netlist:"HlsNetlistCtx", loop_gate: "HlsLoopGate", name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._loop_gate = loop_gate
        self._addOutput(BIT, "busy")

    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        :note: drive of this register is generated from :class:`~.HlsLoopGate`
        """
        op_out = self._outputs[0]

        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass

        name = self.name
        g = self._loop_gate
        statusBusyReg = allocator._reg(
            name if name else f"{self._loop_gate.name}_busy",
            def_val=0 if g.fromEnter else 1)  # busy if is executed at 0 time
        
        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + self.netlist.scheduler.epsilon
        statusBusyReg_s = TimeIndependentRtlResource(statusBusyReg, t, allocator, False)
        allocator.netNodeToRtl[op_out] = statusBusyReg_s

        return statusBusyReg_s

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        if self._loop_gate is not None:
            yield self._loop_gate

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} (for {self._loop_gate.name})>"


class HlsLoopGate(HlsNetNodeOrderable):
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
        The inputs from pipeline are fromEnter and the inputs from out of pipeline are fromReenter.
    
    :ivar fromEnter: for each direct predecessor which is not in cycle body a tuple input for control and variable values.
        Signalizes that the loop has data to be executed.
    :ivar fromReenter: For each direct predecessor which is a part of a cycle body a tuple control input and associated variables.
        Note that the channels are usually connected to out of pipeline interface because the HlsNetlistCtx does not support cycles.
    :ivar fromExit: For each block which is part of the cycle body and does have transition outside of the cycle a control input
        to mark the return of the synchronization token.
    :ivar to_successors: For each direct successor which is not the entry point of the loop body (because of structural programming there can be only one)
        a tuple of control and variable outputs.

    :note: if this gate has synchronization token it accepts only data from the fromEnter and then it accepts only from fromReenter/fromExit
    :note: fromEnter, fromReenter are read at the beginning of a loop header block. Breaks are read at the end of exit block.
    
    :ivar _sync_token_status: The node with state for this object.
    :attention: There should be ordering connected from last IO in the loop to achieve better results in
        :meth:`~.HlsLoopGate.scheduleAlapCompaction` because without it this does not have any outputs and will stay at the end of current cycle
        which is sub-optimal if the whole loop shifts in time.
    """

    def __init__(self, netlist:"HlsNetlistCtx",
            name:Optional[str]=None):
        if name is None:
            name = f"loop{self._id}"
        HlsNetNode.__init__(self, netlist, name=name)
        self.fromEnter: List[HlsNetNodeIn] = []
        self.fromReenter: List[HlsNetNodeIn] = []
        self.fromExit: List[HlsNetNodeIn] = []
        # another node with the output representing the presence of sync token (we can not add it here
        # because it would create a cycle)
        self._sync_token_status = HlsLoopGateStatus(netlist, self)
        self.debugUseNamedSignalsForControl = False
        self._allocated = False

    def _removeInput(self, i:int):
        raise NotImplementedError()

    def _connect(self, control:HlsNetNodeOut, inList: List[HlsNetNodeIn], name: str):
        i = self._addInput(name)
        link_hls_nodes(control, i)
        inList.append(i)

    def connectEnter(self, control:HlsNetNodeOut):
        """
        Register connection of control and data from some block which causes the loop to to execute.
        :note: allocating the sync token
        """
        self._connect(control, self.fromEnter, f"enter{len(self.fromEnter)}")

    def connectReenter(self, control:HlsNetNodeOut):
        """
        Register connection of control and data from some block where control flow gets back block where the cycle starts.
        :note: reusing sync token
        """
        self._connect(control, self.fromReenter, f"reenter{len(self.fromReenter)}")

    def connectExit(self, control: HlsNetNodeOut):
        """
        Register connection of control which causes to break current execution of the loop.
        :note: deallocating the sync token
        :note: the loop may not end this implies that this may not be used at all
        """
        assert isinstance(control.obj, HlsNetNodeExplicitSync), control
        netlist = self.netlist
        vld = netlist.builder.buildReadSync(control.obj.dependsOn[0]) 
        control.obj.addControlSerialSkipWhen(netlist.builder.buildNot(vld))
        
        en = self.netlist.builder.buildAnd(control, vld)
        self._connect(en, self.fromExit, f"exit{len(self.fromExit)}")

    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def scheduleAlapCompaction(self, endOfLastClk: int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        if outputMinUseTimeGetter is not None:
            raise NotImplementedError(outputMinUseTimeGetter)
        # if it is terminator move to end of clk period
        assert not self.scheduledOut, self
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        self.scheduledIn = tuple(endOfLastClk - ffdelay for _ in self.scheduledIn)
        for dep in self.dependsOn:
            yield dep.obj

    def allocateRtlInstance(self, allocator:"ArchElement"):
        """
        All RTL is generated from :class:`~.HlsLoopGateStatus`
        """
        assert not self._allocated, self
        
        status = self._sync_token_status
        statusBusyReg_s = allocator.instantiateHlsNetNodeOut(status._outputs[0])
        statusBusyReg = statusBusyReg_s.valuesInTime[0].data
        # returns the control token
        fromExit = [allocator.instantiateHlsNetNodeOut(self.dependsOn[i.in_i]) for i in self.fromExit]
        # takes the control token
        fromEnter = [allocator.instantiateHlsNetNodeOut(self.dependsOn[i.in_i]) for i in self.fromEnter]
        # has the priority and does not require sync token (because it already owns it)
        fromReenter = [allocator.instantiateHlsNetNodeOut(self.dependsOn[i.in_i]) for i in self.fromReenter]

        assert fromReenter, (self, "Must have some reenters otherwise this is not the loop")
        useNamedSignals = self.debugUseNamedSignalsForControl
        parentU = self.netlist.parentUnit
        name = self.name
        if not fromExit and not fromEnter:
            # this is infinite loop without predecessor, it will run infinitely but in just one instance
            statusBusyReg(1)
        elif not fromExit and fromEnter:
            # this is an infinite loop which has a predecessor, once started it will be closed for new starts
            # :attention: we pick the data from any time because this is kind of back edge
            newExe = Or(*(p.get(p.timeOffset).data for p in fromEnter))
            if useNamedSignals:
                newExe = rename_signal(parentU, newExe, f"{name}_newExe")
            
            If(newExe,
               statusBusyReg(1)
            )
        elif fromExit and fromEnter:
            # loop with a predecessor and successor
            newExe = Or(*(p.get(p.timeOffset).data for p in fromEnter))
            newExit = Or(*(p.get(p.timeOffset).data for p in fromExit))
            if useNamedSignals:
                newExe = rename_signal(parentU, newExe, f"{name}_newExe")
                newExit = rename_signal(parentU, newExit, f"{name}_newExit")
            
            If(newExe & ~newExit,
               statusBusyReg(1)  # becomes busy
            ).Elif(~newExe & newExit,  #  
               statusBusyReg(0)  # finished work
            )
        elif fromExit and not fromEnter:
            # loop with no predecessor and successor
            newExit = Or(*(p.get(p.timeOffset).data for p in fromExit))
            if useNamedSignals:
                newExit = rename_signal(parentU, newExit, f"{name}_newExit")
            
            If(newExit,
               statusBusyReg(0)  # finished work
            )
        else:
            raise AssertionError("All cases should already be covered in this if", self)

        self._allocated = True

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"
