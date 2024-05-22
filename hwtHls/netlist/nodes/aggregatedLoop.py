from math import inf
from typing import Optional, Generator, List, Tuple

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.schedulableNode import OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedulizationDict, SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwt.pyUtils.typingFuture import override


class HlsNetNodeLoop(HlsNetNodeAggregate):
    """
    A cluster of nodes where all node inputs must be scheduled in a same clock period window to assert desired behavior of IO port.
    """

    @override
    def scheduleAsap(self, pathForDebug:Optional[SetList["HlsNetNode"]],
        beginOfFirstClk:SchedTime,
        outputTimeGetter:Optional[OutputTimeGetter]) -> List[int]:
        if self.scheduledOut is None:
            #if pathForDebug is not None:
            #    if self in pathForDebug:
            #        raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
            #    else:
            #        pathForDebug.append(self)
            #try:
            for n in self._subNodes:
                n: HlsNetNode
                n.scheduleAsap(pathForDebug, beginOfFirstClk, outputTimeGetter)

            self.copySchedulingFromChildren()
            #finally:
            #    if pathForDebug is not None:
            #        pathForDebug.pop()

        self.checkScheduling()
        return self.scheduledOut

    def _getTimeSpan(self) -> Tuple[SchedTime, SchedTime]:
        minTime = inf
        maxTime = -inf
        for n in self.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            n: HlsNetNode
            minTime = min(minTime, min(n.scheduledIn, default=minTime), min(n.scheduledOut, default=minTime))
            maxTime = max(maxTime, max(n.scheduledIn, default=maxTime), max(n.scheduledOut, default=maxTime))

        return minTime, maxTime

    def _getTimeSpanInClkTicks(self, clkPeriod: SchedTime):
        minTime, maxTime = self._getTimeSpan()
        beginClkI = indexOfClkPeriod(minTime, clkPeriod)
        endClkI = indexOfClkPeriod(maxTime, clkPeriod)
        assert beginClkI <= endClkI, (self, beginClkI, "<=", endClkI)
        assert isinstance(minTime, SchedTime)

        return beginClkI, endClkI, minTime, maxTime

    @override
    def scheduleAlapCompaction(self, endOfLastClk:SchedTime, outputMinUseTimeGetter:Optional[OutputMinUseTimeGetter]):
        """
        Schedule loop body by ALAP and if the latency of the loop body is increased shift end of this group to time -1 clk_period boundary.
        Decrease time while the loop body latency is increased. If the latency of loop or/and end time is worse than original use original schedule.
        """

        self.checkScheduling()
        originalSchedule: SchedulizationDict = {}
        self.copyScheduling(originalSchedule)
        bestSchedule = originalSchedule

        netlist = self.netlist
        clkPeriod = netlist.normalizedClkPeriod
        # for oPort in self._outputsInside:
        #    oPort: HlsNetNodeAggregatePortOut
        #    oPort.resetScheduling()

        bestBeginClkI, bestEndClkI, _, initialMaxTime = self._getTimeSpanInClkTicks(clkPeriod)
        endCurClk = endOfLastClk

        prevWasBest = isBest = True
        while True:
            isBest = False
            try:
                self.scheduleAlapCompactionForSubnodes(endCurClk, outputMinUseTimeGetter)
            except TimeConstraintError:
                break  # scheduling impossible, use previous best schedule
            beginClkI, endClkI, _, maxTime = self._getTimeSpanInClkTicks(clkPeriod)
            if maxTime > endCurClk:
                # left side (lower time) of the circuit is blocked an moving end clkI has no effect
                break
            elif bestEndClkI - bestBeginClkI >= endClkI - beginClkI:
                # if ALAP scheduled loop with lower latency store it as a best
                bestSchedule = {}
                self.copyScheduling(bestSchedule)
                isBest = True
            elif prevWasBest:
                # if previous schedule was better
                break
            elif initialMaxTime >= maxTime:
                # if min time is smaller than the beginning
                break

            endCurClk -= clkPeriod
            self.setScheduling(originalSchedule)
            prevWasBest = isBest

        self.setScheduling(bestSchedule)

        self.copySchedulingFromChildren()
        self.checkScheduling()

        scheduledZero, scheduledIn, scheduledOut = originalSchedule[self]
        if self.scheduledZero != scheduledZero or self.scheduledIn != scheduledIn or self.scheduledOut != scheduledOut:
            for dep in self.dependsOn:
                yield dep.obj

    @override
    def scheduleAsapCompaction(self, beginOfFirstClk:SchedTime, outputTimeGetter:Optional[OutputTimeGetter]) -> \
            Generator["HlsNetNode", None, None]:
        """
        Schedule loop body by ASAP and if the latency of the loop body is increased shift begin of this group to time +1 clk_period boundary.
        Increase time while the loop body latency is increased. If the start time is worse than original use original schedule.
        """
        outTimes = self.scheduledOut
        zeroTime = self.scheduledZero
        # self.checkScheduling()
        netlist = self.netlist
        clkPeriod = netlist.normalizedClkPeriod

        bestSchedule = {}
        self.copyScheduling(bestSchedule)
        bestBeginClkI, bestEndClkI, initialMinTime, _ = self._getTimeSpanInClkTicks(clkPeriod)

        prevWasBest = isBest = True
        firstRun = True
        while True:
            prevWasBest = isBest
            isBest = False
            self.resetScheduling()
            self.scheduleAsap(None, beginOfFirstClk, outputTimeGetter)
            beginClkI, endClkI, minTime, _ = self._getTimeSpanInClkTicks(clkPeriod)
            self.copySchedulingFromChildren()
            if any(curOT > prevOT for  prevOT, curOT in zip(outTimes, self.scheduledOut)):
                # any time for output time has increased
                break
            elif minTime < beginOfFirstClk:
                # this schedule can not be used because left side (lower time) side of the circuit overflows
                break

            elif (firstRun and bestEndClkI - bestBeginClkI >= endClkI - beginClkI) or bestEndClkI - bestBeginClkI > endClkI - beginClkI:
                # if ALAP scheduled loop with lower latency store it as a best
                bestSchedule = {}
                self.copyScheduling(bestSchedule)
                isBest = True
            elif prevWasBest:
                # if previous schedule was better
                break
            elif initialMinTime <= minTime:
                # if min time is smaller than the beginning
                break
            firstRun = False
            beginOfFirstClk += clkPeriod

        self.setScheduling(bestSchedule)
        assert self.scheduledZero <= zeroTime, ("asap compact", self, zeroTime, "->", self.scheduledZero)
        # self.checkScheduling()
        if outTimes != self.scheduledOut:
            for uses in self.usedBy:
                for u in uses:
                    yield u.obj
