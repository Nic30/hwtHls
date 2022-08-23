from itertools import zip_longest
from math import inf, isfinite
from typing import List, Optional, Union, Tuple, Generator, Dict

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.uniqList import UniqList
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.scheduler.clk_math import start_of_next_clk_period, start_clk
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.opRealizationMeta import OpRealizationMeta

TimeSpec = Union[float, Tuple[int, ...]]
SchedulizationDict = Dict["HlsNetNode", Tuple[Tuple[int, ...], Tuple[int, ...]]]


class HlsNetNode():
    """
    Abstract class for nodes in circuit which are subject to HLS scheduling

    :ivar name: optional suggested name for this object (for debugging purposes)
    :ivar netlist: reference on parent netlist
    :ivar usedBy: for each output list of operation and its input index which are using this output
    :ivar dependsOn: for each input operation and index of its output with data required
        to perform this operation
    :ivar scheduledIn: final scheduled time of start of operation for each input
    :ivar scheduledOut: final scheduled time of end of operation for each output

    :attention: inputs must be sorted 1st must have lowest latency

    :ivar inputWireDelay: combinational latency before first register
        in component for this operation (for each input)
    :ivar outputWireDelay: combinational latency after last register
        in component for this operation (for each output, 0 corresponds to a same time as input[0])
    :ivar OutputClkTickOffset: number of clk cycles for data to get from input
        to output (for each output, 0 corresponds to a same clock cycle as input[0])

    :ivar _inputs: list of inputs of this node
    :ivar _outputs: list of inputs of this node
    """

    def __init__(self, netlist: "HlsNetlistCtx", name: str=None):
        self.name = name
        self.netlist = netlist
        self._id = netlist.getUniqId()

        self.usedBy: List[List[HlsNetNodeIn]] = []
        self.dependsOn: List[HlsNetNodeOut] = []
        self._inputs: List[HlsNetNodeIn] = []
        self._outputs: List[HlsNetNodeOut] = []

        # True if scheduled to specific time
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledOut: Optional[TimeSpec] = None
        self.realization: Optional[OpRealizationMeta] = None
    
    def destroy(self):
        """
        Delete properties of this object to prevent unintentional use.
        """
        self.usedBy = None
        self.dependsOn = None
        self._inputs = None
        self._outputs = None
        self.scheduledIn = None
        self.scheduledOut = None
    
    def getInputDtype(self, i:int) -> HdlType:
        return self.dependsOn[i]._dtype

    def copyScheduling(self, schedule: SchedulizationDict):
        schedule[self] = (self.scheduledIn, self.scheduledOut)

    def checkScheduling(self):
        """
        Assert that the scheduling is consistent.
        """
        assert self.scheduledIn is not None, self
        assert self.scheduledOut is not None, self
        for i, iT, dep in zip_longest(self._inputs, self.scheduledIn, self.dependsOn):
            assert isinstance(iT, int), (i, iT)
            oT = dep.obj.scheduledOut[dep.out_i]
            assert isinstance(oT, int), (dep, oT)
            assert iT >= oT, (iT, oT, "Input must be scheduled after connected output port.", dep, "->", i)
            assert iT >= 0, (iT, self, i, "Scheduled before start of the time.")
            assert oT >= 0, (oT, dep, "Scheduled before start of the time.")

    def resetScheduling(self):
        self.scheduledIn = None
        self.scheduledOut = None
    
    def moveSchedulingTime(self, offset: int):
        self.scheduledIn = tuple(t + offset for t in self.scheduledIn)
        self.scheduledOut = tuple(t + offset for t in self.scheduledOut)
    
    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        """
        The recursive function of ASAP scheduling
        """
        if self.scheduledOut is None:
            clkPeriod = self.netlist.normalizedClkPeriod
            if self.realization is None:
                # resolve realization if it is not already resolved
                self.resolve_realization()

            if self.dependsOn:
                if pathForDebug is not None:
                    if self in pathForDebug:
                        raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                    else:
                        pathForDebug.append(self)

                input_times = (d.obj.scheduleAsap(pathForDebug)[d.out_i] for d in self.dependsOn)

                # now we have times when the value is available on input
                # and we must resolve the minimal time so each input timing constraints are satisfied
                time_when_all_inputs_present = 0
                for (available_in_time, in_delay, in_cycles) in zip(input_times, self.inputWireDelay, self.inputClkTickOffset):
                    if in_delay >= clkPeriod:
                        raise TimeConstraintError(
                            "Impossible scheduling, clkPeriod too low for ",
                            self.inputWireDelay, self.outputWireDelay, self)
                    
                    next_clk_time = start_of_next_clk_period(available_in_time, clkPeriod)
                    time_budget = next_clk_time - available_in_time
    
                    if in_delay >= time_budget:
                        available_in_time = next_clk_time
    
                    normalized_time = (available_in_time
                                       +in_delay
                                       +in_cycles * clkPeriod)
    
                    if normalized_time >= time_when_all_inputs_present:
                        # latest_input_i = in_i
                        time_when_all_inputs_present = normalized_time
    
                self.scheduledIn = tuple(
                    time_when_all_inputs_present - (in_delay + in_cycles * clkPeriod)
                    for (in_delay, in_cycles) in zip(self.inputWireDelay, self.inputClkTickOffset)
                )
    
                self.scheduledOut = tuple(
                    time_when_all_inputs_present + out_delay + out_cycles * clkPeriod
                    for (out_delay, out_cycles) in zip(self.outputWireDelay, self.outputClkTickOffset)
                )
                if pathForDebug is not None:
                    pathForDebug.pop()
            else:
                self.scheduledIn = tuple(0 for _ in self._inputs)
                self.scheduledOut = tuple(l + clkPeriod * clkL for l, clkL in zip(self.outputWireDelay, self.outputClkTickOffset))
    
        return self.scheduledOut
    
    def _schedulerJumpToPrevCycleIfRequired(self, time: Union[float, int], requestedTime: int,
                                            clkPeriod:int, timeSpacingBeforeClkEnd: int) -> int:
        prevClkEndTime = start_clk(time, clkPeriod) * clkPeriod
        if requestedTime <= prevClkEndTime:
            # must shift whole node sooner in time because the input of input can not be satisfied
            # in a clock cycle where the input is currently scheduled
            time = prevClkEndTime - timeSpacingBeforeClkEnd

        return time

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        """
        Single clock variant (inputClkTickOffset and outputClkTickOffset are all zeros)
        """
        # if all dependencies have inputs scheduled we shedule this node and try successors
        if self.scheduledIn is not None:
            return self.scheduledIn
        for iClkOff in self.inputClkTickOffset:
            assert iClkOff == 0, (iClkOff, "this node should use scheduleAlapCompactionMultiClock instead")
        for oClkOff in self.outputClkTickOffset:
            assert oClkOff == 0, (oClkOff, "this node should use scheduleAlapCompactionMultiClock instead")

        assert self.usedBy, ("Compaction should be called only for nodes with dependencies, others should be moved only manually", self)
        asapIn, asapOut = asapSchedule[self]
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        
        clkPeriod = self.netlist.normalizedClkPeriod
        # epsilon = self.netlist.scheduler.epsilon

        # resolve a minimal time where the output can be scheduler and translate it to nodeZeroTime
        nodeZeroTime = inf
        maxLatencyPre = self.inputWireDelay[0] if self.inputWireDelay else 0
        
        for (asapOutT, uses, outWireLatency) in zip(asapOut, self.usedBy, self.outputWireDelay):
            if maxLatencyPre + outWireLatency + ffdelay >= clkPeriod:
                    raise TimeConstraintError(
                        "Impossible scheduling, clkPeriod too low for ",
                        self.outputWireDelay, ffdelay, clkPeriod, self)
            asapOutT: Union[float, int]
            if uses:
                oZeroT = inf 
                # find earliest time where this output is used
                for dependentIn in uses:
                    dependentIn: HlsNetNodeIn
                    iT = dependentIn.obj.scheduleAlapCompaction(asapSchedule)[dependentIn.in_i]
                    zeroTFromInput = iT - outWireLatency
                    zeroTFromInput = self._schedulerJumpToPrevCycleIfRequired(
                        iT, zeroTFromInput, clkPeriod, ffdelay + outWireLatency) - outWireLatency
                    # zeroTFromInput is in previous clk ffdelay + outWireLatency from the end
                    oZeroT = min(oZeroT, zeroTFromInput)
            else:
                # the port is unused we must first check other outputs
                oTSuggestedByAsap = start_of_next_clk_period(asapOutT, clkPeriod) - ffdelay
                oZeroT = oTSuggestedByAsap

            nodeZeroTime = min(nodeZeroTime, oZeroT)

        maxOutputLatency = max(self.outputWireDelay, default=0)
        if isfinite(nodeZeroTime):
            # we have to check if every input has enough time for its delay
            # and optionally move this node to previous clock cycle
            for in_delay in self.inputWireDelay:
                if in_delay + ffdelay >= clkPeriod:
                    raise TimeConstraintError(
                        "Impossible scheduling, clkPeriod too low for ",
                        self.inputWireDelay, self)
                inTime = nodeZeroTime - in_delay
                nodeZeroTime = self._schedulerJumpToPrevCycleIfRequired(
                    nodeZeroTime, inTime, clkPeriod, ffdelay + maxOutputLatency)
                # must shift whole node sooner in time because the input of input can not be satisfied
                # in a clock cycle where the input is currently scheduled
        else:
            # no outputs, we must use some asap input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port")
            nodeZeroTime = start_of_next_clk_period(asapIn[0], clkPeriod) - (ffdelay + maxOutputLatency)
        
        self.scheduledIn = tuple(
            nodeZeroTime - in_delay
            for in_delay in self.inputWireDelay
        )
    
        self.scheduledOut = tuple(
            nodeZeroTime + out_delay
            for out_delay in self.outputWireDelay
        )
        return self.scheduledIn

    def scheduleAlapCompactionMultiClock(self, asapSchedule: SchedulizationDict):
        # if all dependencies have inputs scheduled we schedule this node and try successors
        if self.scheduledIn is not None:
            return self.scheduledIn

        assert self.usedBy, ("Compaction should be called only for nodes with dependencies, others should be moved only manually", self)
        asapIn, asapOut = asapSchedule[self]
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        clkPeriod = self.netlist.normalizedClkPeriod
        epsilon = self.netlist.scheduler.epsilon
        
        # move back in time to satisfy all output timing requirements
        timeOffset = inf
        for uses, oDelay, oTicks in zip(self.usedBy, self.outputWireDelay, self.outputClkTickOffset):
            # find earliest time where this output is used
            if uses:
                oT = inf 
                if uses:
                    for dependentIn in uses:
                        dependentIn: HlsNetNodeIn
                        iT = dependentIn.obj.scheduleAlapCompaction(asapSchedule)[dependentIn.in_i]
                        oT = min(oT, iT - oDelay)

                    if oTicks:
                        # resolve timeOffset as a latest time in this clock cycle - oTicks
                        oT = start_of_next_clk_period(oT, clkPeriod) - clkPeriod * oTicks - ffdelay - epsilon
            else:
                # the port is unused we must first check other outputs
                oT = inf

            timeOffset = min(timeOffset, oT)

        if isfinite(timeOffset):
            # we have to check if every input has enough time for its delay
            # and optionally move this node to previous clock cycle
            for iDelay in self.inputWireDelay:
                if iDelay + ffdelay >= clkPeriod:
                    raise TimeConstraintError(
                        "Impossible scheduling, clkPeriod too low for ",
                        self.inputWireDelay, self.outputWireDelay, self)
                inTime = timeOffset - iDelay
                prevClkEndTime = start_clk(timeOffset, clkPeriod) * clkPeriod

                if inTime <= prevClkEndTime:
                    # must shift whole node sooner in time because the input of input can not be satisfied
                    # in a clock cycle where the input is currently scheduled
                    timeOffset = start_clk(timeOffset, clkPeriod) * clkPeriod - ffdelay - epsilon

        else:
            raise NotImplementedError()
            # no outputs, we must use some asap input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port")
            timeOffset = start_of_next_clk_period(asapIn[0], clkPeriod) - ffdelay - epsilon
        
        inTime = self._scheduleAlapCompactionMultiClockInTime
        self.scheduledIn = tuple(
            inTime(timeOffset, clkPeriod, iTicks, epsilon, ffdelay) - iDelay
            for (iDelay, iTicks) in zip(self.inputWireDelay, self.inputClkTickOffset)
        )
        outTime = self._scheduleAlapCompactionMultiClockOutTime
        self.scheduledOut = tuple(
            outTime(timeOffset, clkPeriod, oTicks) + oDelay
            for (oDelay, oTicks) in zip(self.outputWireDelay, self.outputClkTickOffset)
        )
        return self.scheduledIn
    
    @staticmethod
    def _scheduleAlapCompactionMultiClockInTime(time: int, clkPeriod: int, ticks: int, epsilon: int, ffDelay: int):
        if ticks == 0:
            return time  # was checked that this does not cross clk boundary
        else:
            # if this we substract the clock periods and we end up at the end of clk, from there we alo need to subtract wire delay, etc
            return (start_clk(time, clkPeriod) + ticks - 1) * clkPeriod - epsilon - ffDelay
            
    def _scheduleAlapCompactionMultiClockOutTime(self, time: int, clkPeriod: int, ticks: int):
        if ticks == 0:
            return time
        else:
            return start_of_next_clk_period(time, clkPeriod) + (ticks - 1) * clkPeriod
        
    def iterScheduledClocks(self):
        clkPeriod = self.netlist.normalizedClkPeriod
        beginTime = inf
        endTime = 0
        for i in self.scheduledIn:
            beginTime = min(beginTime, i)
            
        for o in self.scheduledOut:
            endTime = max(endTime, o)
        if not self.scheduledIn:
            beginTime = endTime
        
        startClkI = start_clk(beginTime, clkPeriod)
        endClkI = int(endTime // clkPeriod)
        yield from range(startClkI, endClkI + 1)

    def _removeInput(self, i:int):
        """
        :attention: does not disconnect the input
        """
        self._inputs.pop(i)
        self.dependsOn.pop(i)
        for i in self._inputs[i:]:
            i.in_i -= 1

    def _addInput(self, name: Optional[str]) -> HlsNetNodeIn:
        i = HlsNetNodeIn(self, len(self._inputs), name)
        self.dependsOn.append(None)
        self._inputs.append(i)
        return i

    def _addOutput(self, t: HdlType, name: Optional[str]):
        self.usedBy.append([])
        o = HlsNetNodeOut(self, len(self._outputs), t, name)
        self._outputs.append(o)
        return o

    def assignRealization(self, r: OpRealizationMeta):
        # [todo] move inputWireDelay, outputWireDelay checks for clkPeriod there
        schedulerResolution: float = self.netlist.scheduler.resolution
        self.realization = r
        self.inputClkTickOffset = HlsNetNode_numberForEachInput(self, r.inputClkTickOffset)
        if self.inputClkTickOffset:
            for c in self.inputClkTickOffset:
                assert c >= 0 and c >= self.inputClkTickOffset[0]

        self.inputWireDelay = HlsNetNode_numberForEachInputNormalized(self, r.inputWireDelay, schedulerResolution)
        if self.inputWireDelay:
            for l in self.inputWireDelay:
                assert l <= self.inputWireDelay[0]

        self.outputWireDelay = HlsNetNode_numberForEachOutputNormalized(self, r.outputWireDelay, schedulerResolution)
        self.outputClkTickOffset = HlsNetNode_numberForEachOutput(self, r.outputClkTickOffset)

        return self

    def resolve_realization(self):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def allocateRtlInstanceOutDeclr(self, allocator: "ArchElement", o: HlsNetNodeOut, startTime: int) -> TimeIndependentRtlResource:
        assert allocator.netNodeToRtl.get(o, None) is None, ("Must not be redeclared", allocator, o)
        if len(self._outputs) == 1:
            assert o.out_i == 0, o
            name = f"{allocator.namePrefix}forwardDeclr{self._id:d}"
        else:
            name = f"{allocator.namePrefix}forwardDeclr{self._id:d}_{o.out_i:d}"
        s = allocator._sig(name, o._dtype)
        res = allocator.netNodeToRtl[o] = TimeIndependentRtlResource(s, startTime, allocator)
        return res
      
    def allocateRtlInstance(self, allocator: "ArchElement"):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def createSubNodeRefrenceFromPorts(self, beginTime: float, endTime: float,
                                       inputs: List[HlsNetNodeIn], outputs: List[HlsNetNodeOut]) -> "HlsNetNodePartRef":
        raise NotImplementedError(
            "Override this method in derived class", self)

    def partsComplement(self, otherParts: List["HlsNetNodePartRef"]):
        """
        Create a parts which contains the rest of node not contained in otherParts.
        """
        raise NotImplementedError(
            "Override this method in derived class", self)
        
    def _get_rtl_context(self):
        return self.netlist.ctx

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        """
        Iter nodes which are not connected or somehow related to this but do not use a standard connection.
        (The information is used for visualization.)
        """
        return
        yield


def HlsNetNode_numberForEachInput(node: HlsNetNode, val: Union[float, Tuple[float]]) -> Tuple[Union[int, float]]:
    if isinstance(val, (float, int)):
        return tuple(val for _ in node._inputs)
    else:
        val = list(val)
        assert len(val) == len(node._inputs), (node, val, node._inputs)
        return val


def HlsNetNode_numberForEachOutput(node: HlsNetNode, val: Union[float, Tuple[float]]) -> Tuple[Union[int, float]]:
    if isinstance(val, (float, int)):
        return tuple(val for _ in node._outputs)
    else:
        val = tuple(val)
        assert len(val) == len(node._outputs)
        return val


def HlsNetNode_numberForEachInputNormalized(node: HlsNetNode, val: Union[float, Tuple[float]], scale: float) -> Tuple[int]:
    if isinstance(val, (float, int)):
        return tuple(int(val // scale) for _ in node._inputs)
    else:
        val = tuple(val)
        assert len(val) == len(node._inputs), (node, val, node._inputs)
        return tuple(int(v // scale) for v in val)


def HlsNetNode_numberForEachOutputNormalized(node: HlsNetNode, val: Union[float, Tuple[float]], scale: float) -> Tuple[int]:
    if isinstance(val, (float, int)):
        return tuple(int(val // scale) for _ in node._outputs)
    else:
        val = list(val)
        assert len(val) == len(node._outputs)
        return tuple(int(v // scale) for v in val)


class HlsNetNodePartRef(HlsNetNode):
    """
    Abstract class for references of :class:`~.HlsNetNode` parts.

    :note: The reason for this class is that we need to split nodes during analysis passes when we can not modify the nodes.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentNode: HlsNetNode, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self.parentNode = parentNode
        # deleting because real value is stored in parent node and this is just reference
        self._inputs = None
        self._outputs = None
        self.dependsOn = None
        self.usedBy = None
        self.scheduledIn = None
        self.scheduledOut = None

