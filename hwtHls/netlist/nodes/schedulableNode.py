from itertools import zip_longest
from math import inf, isfinite
from typing import Tuple, Dict, Optional, Callable, Union, Literal, List, \
    Generator

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.observableList import ObservableList
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, start_clk
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.opRealizationMeta import OpRealizationMeta

SchedulizationDict = Dict["HlsNetNode", Tuple[int,  # node zero time
                                              Tuple[int, ...],  # scheduledIn
                                              Tuple[int, ...]]]  # scheduledOut
TimeSpec = Union[float, Tuple[int, ...]]
OutputMinUseTimeGetter = Callable[[HlsNetNodeOut, Union[int, Literal[inf]]], int]  # second parameter is a current min time resolved from inputs
OutputTimeGetter = Callable[[HlsNetNodeOut, Optional[UniqList["HlsNetNode"]], int], int]  # 2. parameter is path of nodes for debug of cycles, 3. parameter is beginOfFirstClk


class SchedulableNode():

    def __init__(self, netlist: "HlsNetlistCtx"):
        self.netlist = netlist
        self.usedBy: List[List[HlsNetNodeIn]] = []
        self.dependsOn: ObservableList[HlsNetNodeOut] = ObservableList()
        self._inputs: List[HlsNetNodeIn] = []
        self._outputs: ObservableList[HlsNetNodeOut] = ObservableList()

        self.scheduledZero: Optional[int] = None
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledOut: Optional[TimeSpec] = None
        self.realization: Optional[OpRealizationMeta] = None
        self.isMulticlock: bool = False

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

    @staticmethod
    def _schedulerGetNormalizedTimeForInput(availableInTime: int, inWireLatency: int, inputClkTickOffset: int, clkPeriod: int, ffdelay: int):
        """
        :param availableInTime: time when all dependencies of input are available
        :param inWireLatency: time which must be available before clock cycle
        :param inputClkTickOffset: number of clock cycles between clock cycle where this input is and where node zero time is
        :param clkPeriod: normalized clock period
        :param ffdelay: normalized time of register store operation

        :return: normalized time of where node zero time is according this input
        """
        nextClkTime = (indexOfClkPeriod(availableInTime, clkPeriod) + 1) * clkPeriod
        timeBudget = nextClkTime - availableInTime - ffdelay

        if inWireLatency > timeBudget:
            availableInTime = nextClkTime

        # [fixme] in_cycles is not used correctly
        normalizedTime = (availableInTime
                          +inWireLatency
                          +inputClkTickOffset * clkPeriod)
        return normalizedTime

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]],
                     beginOfFirstClk: int,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        """
        The recursive function of As Soon As Possible scheduling. Initial netlist scheduling method.
        """
        if self.scheduledOut is None:
            netlist = self.netlist
            clkPeriod = netlist.normalizedClkPeriod
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
                        inputTimes = (d.obj.scheduleAsap(pathForDebug, beginOfFirstClk, None)[d.out_i]
                                       for d in self.dependsOn)
                    else:
                        inputTimes = (outputTimeGetter(d, pathForDebug, beginOfFirstClk) for d in self.dependsOn)

                    inputTimes = tuple(inputTimes)
                    ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
                    # now we have times when the value is available on input
                    # and we must resolve the minimal time so each input timing constraints are satisfied
                    nodeZeroTime = beginOfFirstClk
                    for (availableInTime, inWireLatency, inputClkTickOffset) in zip(inputTimes, self.inputWireDelay, self.inputClkTickOffset):
                        if inWireLatency >= clkPeriod:
                            raise TimeConstraintError(
                                "Impossible scheduling, clkPeriod too low for ",
                                self.inputWireDelay, self.outputWireDelay, self)
                        normalizedTime = self._schedulerGetNormalizedTimeForInput(
                            availableInTime, inWireLatency, inputClkTickOffset, clkPeriod, ffdelay)

                        if normalizedTime >= nodeZeroTime:
                            nodeZeroTime = normalizedTime
                finally:
                    if pathForDebug is not None:
                        pathForDebug.pop()
            else:
                assert not self._inputs
                nodeZeroTime = beginOfFirstClk

            if self.isMulticlock:
                epsilon = netlist.scheduler.epsilon
                self._setScheduleZeroTimeMultiClock(nodeZeroTime, clkPeriod, epsilon, ffdelay)
            else:
                self._setScheduleZeroTimeSingleClock(nodeZeroTime)

        return self.scheduledOut

    def scheduleAlapCompaction(self, endOfLastClk: int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter])\
            ->Generator["HlsNetNode", None, None]:
        """
        Single clock variant (inputClkTickOffset and outputClkTickOffset are all zeros)

        :return: a generator of dependencies which are now possible subject to compaction.
        """
        assert not self.isMulticlock, (self, "this node should use scheduleAlapCompactionMultiClock instead")

        # assert self.usedBy, ("Compaction should be called only for nodes with dependencies, others should be moved only manually", self)
        netlist = self.netlist
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
        clkPeriod = netlist.normalizedClkPeriod
        if not self._outputs:
            # no outputs, we must use some asap input time and move to end of the clock
            assert self._inputs, (self, "Node must have at least some port.")
            nodeZeroTime = inf
        else:
            # resolve a minimal time where the output can be scheduler and translate it to nodeZeroTime
            nodeZeroTime = inf
            maxLatencyPre = self.inputWireDelay[0] if self.inputWireDelay else 0

            curZero = self.scheduledZero
            for (out, uses, outWireLatency) in zip(self._outputs, self.usedBy, self.outputWireDelay):
                if maxLatencyPre + outWireLatency + ffdelay >= clkPeriod:
                        raise TimeConstraintError(
                            "Impossible scheduling, clkPeriod too low for ",
                            self.outputWireDelay, ffdelay, clkPeriod, self)
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
        Move node to a later time if possible. Netlist is expected to be scheduled.
        This allows to move trees of nodes to later times and allow for possibly better fit of nodes
        to a clock period windows.

        :return: generator of nodes for compaction worklist
        """
        assert self.isMulticlock, self
        # if all dependencies have inputs scheduled we schedule this node and try successors
        netlist = self.netlist
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
        clkPeriod = netlist.normalizedClkPeriod
        epsilon = netlist.scheduler.epsilon
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

    def scheduleAsapCompaction(self, beginOfFirstClk:int, outputTimeGetter:Optional[OutputTimeGetter]) -> \
            Generator["HlsNetNode", None, None]:
        outTimes = self.scheduledOut
        zeroTime = self.scheduledZero
        # self.checkScheduling()
        schedule = {}
        self.copyScheduling(schedule)
        self.resetScheduling()
        self.scheduleAsap(None, beginOfFirstClk, outputTimeGetter)
        if any(curOT > prevOT for  prevOT, curOT in zip(outTimes, self.scheduledOut)):
            self.setScheduling(schedule)
            return
        # for prevOT, curOT, o in zip(outTimes, self.scheduledOut, self._outputs):
        #    assert prevOT >= curOT, ("asap compact", o, prevOT, "->", curOT)
        assert self.scheduledZero <= zeroTime, ("asap compact", self, zeroTime, "->", self.scheduledZero)
        # self.checkScheduling()
        if outTimes != self.scheduledOut:
            for uses in self.usedBy:
                for u in uses:
                    yield u.obj

    # def scheduleAsapCompaction(self, beginOfFirstClk: int, outputTimeGetter: Optional[OutputTimeGetter])\
    #        ->Generator["HlsNetNode", None, None]:
    #    """
    #    Single clock variant (inputClkTickOffset and outputClkTickOffset are all zeros)
    #
    #    :return: a generator of dependencies which are now possible subject to compaction.
    #    """
    #    assert not self.isMulticlock, (self, "this node should use scheduleAsapCompactionMultiClock instead")
    #    netlist = self.netlist
    #    ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
    #    clkPeriod = netlist.normalizedClkPeriod
    #    if not self._inputs:
    #        # no outputs, we must use some asap input time and move to end of the clock
    #        assert self._inputs, (self, "Node must have at least some port.")
    #        nodeZeroTime = beginOfFirstClk
    #    else:
    #        # resolve a minimal time where the output can be scheduler and translate it to nodeZeroTime
    #        nodeZeroTime = beginOfFirstClk
    #
    #        curZero = self.scheduledZero
    #        for (dependentIn, dep, inWireLatency, inputClkTickOffset) in zip(
    #                self._inputs, self.dependsOn, self.inputWireDelay, self.inputClkTickOffset):
    #            dependentIn: HlsNetNodeIn
    #            dep: HlsNetNodeOut
    #            # find earliest time where this output is used
    #            if outputTimeGetter is None:
    #                availableInTime = dep.obj.scheduledOut[dep.out_i]
    #            else:
    #                availableInTime = outputTimeGetter(dep, None, beginOfFirstClk)
    #
    #            if outputTimeGetter is not None:
    #                availableInTime = outputTimeGetter(dep, availableInTime)
    #            # if curZero is not None:
    #            #     assert availableInTime >= curZero, (availableInTime, curZero, self.scheduledIn[dependentIn.in_i], "Output time violates input arrival time.", self, dep, dependentIn)
    #
    #            normalizedTime = self._schedulerGetNormalizedTimeForInput(
    #                availableInTime, inWireLatency, inputClkTickOffset, clkPeriod, ffdelay)
    #
    #            if normalizedTime > nodeZeroTime:
    #                nodeZeroTime = normalizedTime
    #
    #    if self.scheduledZero != nodeZeroTime:
    #        assert isinstance(nodeZeroTime, int) and (self.scheduledZero is None or (isinstance(self.scheduledZero, int))
    #                ), (self.scheduledZero, "->", nodeZeroTime, self)
    #
    #        if self.scheduledZero is not None and self.scheduledZero > nodeZeroTime:
    #            # this can happen if successor nodes were packed inefficiently in previous cycles and it moved this node
    #            # we can not move this node because it would potentially move whole circuit which would eventually result
    #            # in an endless cycle in scheduling
    #            raise TimeConstraintError(
    #                   "Can not be scheduled later then current best ASAP time because otherwise time should have been kept", self)
    #
    #        if self.isMulticlock:
    #            epsilon = netlist.scheduler.epsilon
    #            self._setScheduleZeroTimeMultiClock(nodeZeroTime, clkPeriod, epsilon, ffdelay)
    #        else:
    #            self._setScheduleZeroTimeSingleClock(nodeZeroTime)
    #
    #        for uses in self.usedBy:
    #            for u in uses:
    #                yield u.obj

    def iterScheduledClocks(self):
        clkPeriod = self.netlist.normalizedClkPeriod

        if self.scheduledIn is None and self.scheduledOut is None:
            endTime = beginTime = self.scheduledZero
            pass  # part ref
        else:
            endTime = beginTime = self.scheduledZero
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
