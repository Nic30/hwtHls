from itertools import zip_longest
from math import inf, isfinite
from typing import List, Optional, Union, Tuple, Generator, Dict, Callable, \
    Literal

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.uniqList import UniqList
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.observableList import ObservableList
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, start_clk
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.opRealizationMeta import OpRealizationMeta

TimeSpec = Union[float, Tuple[int, ...]]
SchedulizationDict = Dict["HlsNetNode", Tuple[int,  # node zero time
                                              Tuple[int, ...],  # scheduledIn
                                              Tuple[int, ...]]]  # scheduledOut
OutputMinUseTimeGetter = Callable[[HlsNetNodeOut, Union[int, Literal[inf]]], int]  # second parameter is a current min time resolved from inputs
OutputTimeGetter = Callable[[HlsNetNodeOut, Optional[UniqList["HlsNetNode"]], int], int]  # 2. parameter is path of nodes for debug of cycles, 3. parameter is beginOfFirstClk


def _tupleWithoutItemOnIndex(arr: tuple, index: int):
    return tuple(item for i, item in enumerate(arr) if i != index)


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
        self.dependsOn: ObservableList[HlsNetNodeOut] = ObservableList()
        self._inputs: List[HlsNetNodeIn] = []
        self._outputs: List[HlsNetNodeOut] = []

        # True if scheduled to specific time
        self.scheduledZero: Optional[int] = None
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledOut: Optional[TimeSpec] = None
        self.realization: Optional[OpRealizationMeta] = None
        self.isMulticlock: bool = False
    
    def destroy(self):
        """
        Delete properties of this object to prevent unintentional use.
        """
        self.usedBy = None
        self.dependsOn = None
        self._inputs = None
        self._outputs = None
        self.scheduledZero = None
        self.scheduledIn = None
        self.scheduledOut = None
    
    def getInputDtype(self, i:int) -> HdlType:
        return self.dependsOn[i]._dtype

    def copyScheduling(self, schedule: SchedulizationDict):
        schedule[self] = (self.scheduledZero, self.scheduledIn, self.scheduledOut)

    def setScheduling(self, schedule: SchedulizationDict):
        (self.scheduledZero, self.scheduledIn, self.scheduledOut) = schedule[self]

    def checkScheduling(self):
        """
        Assert that the scheduling is consistent.
        """
        assert self.scheduledZero is not None, self
        assert self.scheduledIn is not None, self
        assert self.scheduledOut is not None, self
        for i, iT, dep in zip_longest(self._inputs, self.scheduledIn, self.dependsOn):
            assert isinstance(iT, int), (self, i, dep, iT)
            assert dep is not None, (self, i, dep, "Inconsistent input specification")
            assert i is not None, (self, dep, "Inconsistent input specification")
            assert dep.obj.scheduledOut is not None, (self, dep.obj)
            oT = dep.obj.scheduledOut[dep.out_i]
            assert isinstance(oT, int), (dep, oT)
            assert iT >= oT, (oT, iT, "Input must be scheduled after connected output port.", dep, "->", i)
            assert iT >= 0, (iT, self, i, "Scheduled before start of the time.")
            assert oT >= 0, (oT, dep, "Scheduled before start of the time.")

    def resetScheduling(self):
        self.scheduledZero = None
        self.scheduledIn = None
        self.scheduledOut = None
    
    def moveSchedulingTime(self, offset: int):
        self.scheduledZero += offset
        self.scheduledIn = tuple(t + offset for t in self.scheduledIn)
        self.scheduledOut = tuple(t + offset for t in self.scheduledOut)
    
    def _setScheduleZeroTimeSingleClock(self, t: int):
        assert isinstance(t, int), t
        assert self.scheduledZero != t, (self, t)
        self.scheduledZero = t
        self.scheduledIn = tuple(
            t - in_delay
            for in_delay in self.inputWireDelay
        )
        self.scheduledOut = tuple(
            t + out_delay
            for out_delay in self.outputWireDelay
        )

    def _setScheduleZeroTimeMultiClock(self, t: int, clkPeriod: int, epsilon: int, ffdelay):
        assert isinstance(t, int), t
        assert self.scheduledZero != t, (self, t)
        self.scheduledZero = t
        inTime = self._scheduleAlapCompactionMultiClockInTime
        self.scheduledIn = tuple(
            inTime(t, clkPeriod, iTicks, epsilon, ffdelay) - iDelay
            for (iDelay, iTicks) in zip(self.inputWireDelay, self.inputClkTickOffset)
        )
        outTime = self._scheduleAlapCompactionMultiClockOutTime
        self.scheduledOut = tuple(
            outTime(t, clkPeriod, oTicks) + oDelay
            for (oDelay, oTicks) in zip(self.outputWireDelay, self.outputClkTickOffset)
        )

    @staticmethod
    def _scheduleAlapCompactionMultiClockInTime(time: int, clkPeriod: int, ticks: int, epsilon: int, ffDelay: int):
        if ticks == 0:
            return time  # was checked that this does not cross clk boundary
        else:
            # if this we substract the clock periods and we end up at the end of clk, from there we alo need to subtract wire delay, etc
            return (indexOfClkPeriod(time, clkPeriod) - ticks + 1) * clkPeriod - epsilon - ffDelay

    @staticmethod
    def _scheduleAlapCompactionMultiClockOutTime(time: int, clkPeriod: int, ticks: int):
        if ticks == 0:
            return time
        else:
            return (indexOfClkPeriod(time, clkPeriod) + ticks) * clkPeriod
        
    @staticmethod
    def _schedulerJumpToPrevCycleIfRequired(time: Union[float, int], requestedTime: int,
                                            clkPeriod:int, timeSpacingBeforeClkEnd: int) -> int:
        prevClkEndTime = indexOfClkPeriod(time, clkPeriod) * clkPeriod
        if requestedTime < prevClkEndTime:
            # must shift whole node sooner in time because the input of input can not be satisfied
            # in a clock cycle where the input is currently scheduled
            time = prevClkEndTime - timeSpacingBeforeClkEnd

        return time
    
    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]],
                     beginOfFirstClk: int,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        """
        The recursive function of ASAP scheduling
        """
        if self.scheduledOut is None:
            clkPeriod = self.netlist.normalizedClkPeriod
            if self.realization is None:
                # resolve realization if it is not already resolved
                self.resolveRealization()

            if self.dependsOn:
                if pathForDebug is not None:
                    if self in pathForDebug:
                        raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                    else:
                        pathForDebug.append(self)
                try:
                    if outputTimeGetter is None:
                        input_times = (d.obj.scheduleAsap(pathForDebug, beginOfFirstClk, None)[d.out_i]
                                       for d in self.dependsOn)
                    else:
                        input_times = (outputTimeGetter(d, pathForDebug, beginOfFirstClk) for d in self.dependsOn)
    
                    input_times = tuple(input_times)

                    ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
                    # now we have times when the value is available on input
                    # and we must resolve the minimal time so each input timing constraints are satisfied
                    nodeZeroTime = beginOfFirstClk
                    for (available_in_time, in_delay, in_cycles) in zip(input_times, self.inputWireDelay, self.inputClkTickOffset):
                        if in_delay >= clkPeriod:
                            raise TimeConstraintError(
                                "Impossible scheduling, clkPeriod too low for ",
                                self.inputWireDelay, self.outputWireDelay, self)
                        
                        next_clk_time = (indexOfClkPeriod(available_in_time, clkPeriod) + 1) * clkPeriod
                        timeBudget = next_clk_time - available_in_time - ffdelay
        
                        if in_delay >= timeBudget:
                            available_in_time = next_clk_time
                        
                        # [fixme] in_cycles is not used correctly
                        normalized_time = (available_in_time
                                           +in_delay
                                           +in_cycles * clkPeriod)
        
                        if normalized_time >= nodeZeroTime:
                            nodeZeroTime = normalized_time
                finally:
                    if pathForDebug is not None:
                        pathForDebug.pop()
            else:
                assert not self._inputs
                nodeZeroTime = beginOfFirstClk

            if self.isMulticlock:
                epsilon = self.netlist.scheduler.epsilon
                self._setScheduleZeroTimeMultiClock(nodeZeroTime, clkPeriod, epsilon, ffdelay)
            else:
                self._setScheduleZeroTimeSingleClock(nodeZeroTime)
    
        return self.scheduledOut

    def scheduleAlapCompaction(self, endOfLastClk: int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]) -> Generator["HlsNetNode", None, None]:
        """
        Single clock variant (inputClkTickOffset and outputClkTickOffset are all zeros)
        
        :return: a generator of dependencies which are now possible subject to compaction.
        """
        # if all dependencies have inputs scheduled we schedule this node and try successors
        for iClkOff in self.inputClkTickOffset:
            assert iClkOff == 0, (iClkOff, "this node should use scheduleAlapCompactionMultiClock instead")
        for oClkOff in self.outputClkTickOffset:
            assert oClkOff == 0, (oClkOff, "this node should use scheduleAlapCompactionMultiClock instead")

        #assert self.usedBy, ("Compaction should be called only for nodes with dependencies, others should be moved only manually", self)
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        clkPeriod = self.netlist.normalizedClkPeriod
        if not self._outputs:
            # no outputs, we must use some asap input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port.")
            nodeZeroTime = inf
        else:
            # resolve a minimal time where the output can be scheduler and translate it to nodeZeroTime
            nodeZeroTime = inf
            maxLatencyPre = self.inputWireDelay[0] if self.inputWireDelay else 0
            
            for (out, uses, outWireLatency) in zip(self._outputs, self.usedBy, self.outputWireDelay):
                if maxLatencyPre + outWireLatency + ffdelay >= clkPeriod:
                        raise TimeConstraintError(
                            "Impossible scheduling, clkPeriod too low for ",
                            self.outputWireDelay, ffdelay, clkPeriod, self)
                curZero = self.scheduledZero
                if uses:
                    oZeroT = inf 
                    # find earliest time where this output is used
                    for dependentIn in uses:
                        dependentIn: HlsNetNodeIn
                        iT = dependentIn.obj.scheduledIn[dependentIn.in_i]
                        if curZero is not None:
                            assert iT >= curZero, (iT, curZero, self.scheduledOut[out.out_i], "Output time violates input arrival time.", out, dependentIn)
                        zeroTFromInput = iT - outWireLatency
                        zeroTFromInput = self._schedulerJumpToPrevCycleIfRequired(
                            iT, zeroTFromInput, clkPeriod, ffdelay + outWireLatency) - outWireLatency
                        # zeroTFromInput is in previous clk ffdelay + outWireLatency from the end
                        oZeroT = min(oZeroT, zeroTFromInput)
                else:
                    # there are some other uses we may skip this
                    oZeroT = inf
    
                if outputMinUseTimeGetter is not None:
                    oZeroT = outputMinUseTimeGetter(out, oZeroT)
    
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
            # no use of any output, we must use some ASAP input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port used")
            nodeZeroTime = endOfLastClk - (ffdelay + maxOutputLatency)

        if self.scheduledZero != nodeZeroTime:
            assert isinstance(nodeZeroTime, int) and (self.scheduledZero is None or (isinstance(self.scheduledZero, int))
                    ), (self.scheduledZero, "->", nodeZeroTime, self)
            
            if self.scheduledZero is not None and self.scheduledZero > nodeZeroTime:
                # this can happen if successor nodes were packed inefficiently in previous cycles and it moved this node
                # we can not move this node because it would potentially move whole circuit which would eventually result
                # in an endless cycle in scheduling
                raise TimeConstraintError(
                       "Can not be scheduled sooner then current best ALAP time because otherwise time should have been kept", self)
            self._setScheduleZeroTimeSingleClock(nodeZeroTime)
            for dep in self.dependsOn:
                yield dep.obj

    def scheduleAlapCompactionMultiClock(self, endOfLastClk: int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]) -> Generator["HlsNetNode", None, None]:
        """
        Move node to a later time if possible.
        """
        # if all dependencies have inputs scheduled we schedule this node and try successors
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        clkPeriod = self.netlist.normalizedClkPeriod
        epsilon = self.netlist.scheduler.epsilon
        if not self._outputs or not any(self.usedBy):
            # no outputs, we must use some asap input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port.")
            nodeZeroTime = endOfLastClk - ffdelay - epsilon
        
        else:
            # move back in time to satisfy all output timing requirements
            nodeZeroTime = inf
            for out, uses, oDelay, oTicks in zip(self._outputs, self.usedBy, self.outputWireDelay, self.outputClkTickOffset):
                # find earliest time where this output is used
                if uses:
                    oT = inf 
                    if uses:
                        for dependentIn in uses:
                            dependentIn: HlsNetNodeIn
                            iT = dependentIn.obj.scheduledIn[dependentIn.in_i]
                            oT = min(oT, iT - oDelay)
    
                        if oTicks:
                            # resolve nodeZeroTime as a latest time in this clock cycle - oTicks
                            oT = (indexOfClkPeriod(oT, clkPeriod) + 1 - oTicks) * clkPeriod - ffdelay - epsilon
                else:
                    # the port is unused we must first check other outputs
                    oT = inf
                if outputMinUseTimeGetter is not None:
                    oT = outputMinUseTimeGetter(out, oT)
                nodeZeroTime = min(nodeZeroTime, oT)
    
            assert isfinite(nodeZeroTime), (self, "Must be finite because we already checked that there is some use.")
            # we have to check if every input has enough time for its delay
            # and optionally move this node to previous clock cycle
            for iDelay in self.inputWireDelay:
                if iDelay + ffdelay >= clkPeriod:
                    raise TimeConstraintError(
                        "Impossible scheduling, clkPeriod too low for ",
                        self.inputWireDelay, self.outputWireDelay, self)
                inTime = nodeZeroTime - iDelay
                prevClkEndTime = indexOfClkPeriod(nodeZeroTime, clkPeriod) * clkPeriod
    
                if inTime <= prevClkEndTime:
                    # must shift whole node sooner in time because the input of input can not be satisfied
                    # in a clock cycle where the input is currently scheduled
                    nodeZeroTime = indexOfClkPeriod(nodeZeroTime, clkPeriod) * clkPeriod - ffdelay - epsilon

        if nodeZeroTime > self.scheduledZero:
            self._setScheduleZeroTimeMultiClock(nodeZeroTime, clkPeriod, epsilon, ffdelay)
            for dep in self.dependsOn:
                yield dep.obj
    
    def iterScheduledClocks(self):
        clkPeriod = self.netlist.normalizedClkPeriod
        beginTime = inf
        endTime = 0
        assert self.scheduledIn or self.scheduledOut, self
        for i in self.scheduledIn:
            beginTime = min(beginTime, i)
            
        for o in self.scheduledOut:
            endTime = max(endTime, o)
        
        if not self.scheduledIn:
            beginTime = endTime

        if not self.scheduledOut:
            endTime = beginTime
            
        startClkI = start_clk(beginTime, clkPeriod)
        endClkI = int(endTime // clkPeriod)
        yield from range(startClkI, endClkI + 1)

    def _removeInput(self, i: int):
        """
        :attention: does not disconnect the input
        """
        self.dependsOn.pop(i)
        self._inputs.pop(i)
        for inp in self._inputs[i:]:
            inp.in_i -= 1

        if self.realization is not None:
            self.inputClkTickOffset = _tupleWithoutItemOnIndex(self.inputClkTickOffset, i)
            self.inputWireDelay = _tupleWithoutItemOnIndex(self.inputWireDelay, i)
            if self.scheduledIn is not None:
                self.scheduledIn = _tupleWithoutItemOnIndex(self.scheduledIn, i)

    def _removeOutput(self, i: int):
        """
        :attention: does not disconnect the output
        """
        self.usedBy.pop(i)
        self._outputs.pop(i)
        for out in self._outputs[i:]:
            out.out_i -= 1

        if self.realization is not None:
            self.outputClkTickOffset = _tupleWithoutItemOnIndex(self.outputClkTickOffset, i)
            self.outputWireDelay = _tupleWithoutItemOnIndex(self.outputWireDelay, i)
            if self.scheduledOut is not None:
                self.scheduledOut = _tupleWithoutItemOnIndex(self.scheduledOut, i)
        
    def _addInput(self, name: Optional[str]) -> HlsNetNodeIn:
        assert self.realization is None, self
        i = HlsNetNodeIn(self, len(self._inputs), name)
        self._inputs.append(i)
        self.dependsOn.append(None)
        return i

    def _addOutput(self, t: HdlType, name: Optional[str]) -> HlsNetNodeOut:
        assert self.realization is None, self
        o = HlsNetNodeOut(self, len(self._outputs), t, name)
        self._outputs.append(o)
        self.usedBy.append([])
        return o
    
    def deleteRealization(self):
        self.realization = None
        self.inputClkTickOffset = None
        self.inputWireDelay = None
        self.outputWireDelay = None
        self.outputClkTickOffset = None
        self.isMulticlock = None

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
        self.isMulticlock = any(self.inputClkTickOffset) or any(self.outputClkTickOffset)
        iCnt = len(self._inputs)
        assert len(self.inputWireDelay) == iCnt
        assert len(self.inputClkTickOffset) == iCnt
        oCnt = len(self._outputs)
        assert len(self.outputWireDelay) == oCnt
        assert len(self.outputClkTickOffset) == oCnt
        
        return self

    def resolveRealization(self):
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
        res = allocator.netNodeToRtl[o] = TimeIndependentRtlResource(s, startTime, allocator, False)
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

    :note: The reason for this class is that we need to split nodes during analysis passes when we can not modify nodes.
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
        self._subNodes: Optional["HlsNetlistClusterSearch"] = None
    
    def iterChildReads(self):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def iterChildWrites(self):
        raise NotImplementedError(
            "Override this method in derived class", self)
