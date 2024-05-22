from math import inf, isfinite
from typing import Optional, List

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.typingFuture import override


class HlsNetNodeIoSyncScc(HlsNetNodeAggregate):
    """
    A cluster of nodes where all node inputs must be scheduled in a same clock period window to assert desired behavior of IO port.
    """

    @override
    def scheduleAsap(self, pathForDebug: Optional[SetList["HlsNetNode"]], beginOfFirstClk: SchedTime,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[SchedTime]:
        """
        Schedule from defs to uses as is, if everything fits in a single clock cycle the result is final.
        If not reset scheduling and move everything to next clock cycle.
        If the cluster still can fit in clock cycle raise timing error else result is final.
        """

        # get time for all inputs
        # pick the latest clock cycle to start scheduling of this cluster (which must be scheduled in a single clock cycle window).
        if self.scheduledOut is None:
            if pathForDebug is not None:
                if self in pathForDebug:
                    raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                else:
                    pathForDebug.append(self)
            if self._inputs:
                inMaxT = -inf
                for outerDep in self.dependsOn:
                    if outputTimeGetter is None:
                        t = outerDep.obj.scheduleAsap(pathForDebug, beginOfFirstClk, None)[outerDep.out_i]
                    else:
                        t = outputTimeGetter(outerDep, pathForDebug, beginOfFirstClk)
                    assert isinstance(t, int), (t, outerDep)
                    inMaxT = max(inMaxT, t)
            else:
                inMaxT = beginOfFirstClk

            clkPeriod = self.netlist.normalizedClkPeriod
            epsilon = self.netlist.scheduler.epsilon
            moveTried = False
            while True:
                beginOfClkWhereLastInputIs = indexOfClkPeriod(inMaxT, clkPeriod) * clkPeriod
                endOfClkWhereLastInputIs = beginOfClkWhereLastInputIs + clkPeriod - epsilon

                def _outputTimeGetter(out: HlsNetNodeOut, pathForDebug: Optional[SetList["HlsNetNode"]], beginOfFirstClk: int):
                    t = out.obj.scheduleAsap(pathForDebug, max(beginOfFirstClk, beginOfClkWhereLastInputIs), _outputTimeGetter)[out.out_i]
                    return max(t, beginOfClkWhereLastInputIs)

                maxTime = -inf
                schedulingFail = False

                for n in self._subNodes:
                    n: HlsNetNode
                    n.scheduleAsap(pathForDebug, beginOfClkWhereLastInputIs, _outputTimeGetter)
                    if n._inputs:
                        maxTime = max(maxTime, *n.scheduledIn)
                    else:
                        maxTime = max(maxTime, n.scheduledZero)
                    assert n.scheduledZero >= beginOfClkWhereLastInputIs, (n, n.scheduledIn, n.scheduledOut, maxTime, beginOfClkWhereLastInputIs)
                    assert maxTime >= beginOfClkWhereLastInputIs, (n, n.scheduledIn, n.scheduledOut, maxTime, beginOfClkWhereLastInputIs)
                    if maxTime >= endOfClkWhereLastInputIs:
                        schedulingFail = True
                        if not moveTried:
                            # if this is first try we stop scheduling and move to next clock cycle
                            break

                assert isfinite(maxTime), ("Time must be finite because there must to be something in this cluster which should be scheduled in some specific time", self)

                if schedulingFail:
                    # if moveTried:
                    #    from hwtHls.netlist.translation.dumpNodesDot import HwtHlsNetlistToGraphwiz
                    #    toGraphwiz = HwtHlsNetlistToGraphwiz(f"IoScc{self._id:d}", self._subNodes)
                    #    toGraphwiz.construct()
                    #    with open(f"tmp/TimeConstraintError.{toGraphwiz.name:s}.dot", "w") as f:
                    #        f.write(toGraphwiz.dumps())
                    #
                    #     raise TimeConstraintError(
                    #        "Impossible scheduling, clkPeriod too low IO synchronization realization ",
                    #        self, " discovered on ", n)

                    if moveTried:
                        break
                    self.resetScheduling()
                    moveTried = True
                    assert inMaxT < maxTime, (inMaxT, "->", maxTime)
                    inMaxT = maxTime
                else:
                    break

            self.copySchedulingFromChildren()
        self.checkScheduling()
        return self.scheduledOut

    @override
    def checkScheduling(self):
        HlsNetNodeAggregate.checkScheduling(self)
        clkPeriod = self.netlist.normalizedClkPeriod
        beginOfClk = indexOfClkPeriod(self.scheduledZero, clkPeriod) * clkPeriod
        endOfClk = beginOfClk + clkPeriod
        for t in self.scheduledIn:
            assert t >= beginOfClk and t < endOfClk, (self, (beginOfClk, endOfClk), self.scheduledIn)

    @override
    def scheduleAlapCompaction(self, endOfLastClk: SchedTime, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        """
        Use the same principle as :meth:`~.HlsNetNodeIoSyncScc.scheduleAsap` just schedule from uses to defs.
        In addition there may be internal and also outer uses of a single output and we have to resolve scheduling time from all uses.
        """
        self.checkScheduling()
        prevSchedule: SchedulizationDict = {}
        self.copyScheduling(prevSchedule)

        epsilon = self.netlist.scheduler.epsilon
        clkPeriod = self.netlist.normalizedClkPeriod
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        # find the most constraining port
        minClkI = inf
        for oPort in self._outputsInside:
            oPort: HlsNetNodeAggregatePortOut
            oPort.resetScheduling()
            assert not any(oPort.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter))
            minClkI = min(minClkI, indexOfClkPeriod(oPort.scheduledIn[0], clkPeriod))

        assert isinstance(minClkI, int), minClkI
        moveToPrevClkTried = False
        lastSchedule:SchedulizationDict = {}
        # move outputs to a clock where first output is required,
        # if move failed move -1 clk if fails again it is not possible to move and original scheduling must be restored
        while True:
            # move all outputs to same time as most constraining port
            endCurClk = (minClkI + 1) * clkPeriod - ffdelay
            # for oPort in self._outputsInside:
            #    oPort: HlsNetNodeAggregatePortOut
            #    if oPort.scheduledZero is None or oPort.scheduledZero > endCurClk:
            #        oPort._setScheduleZero(endCurClk)
            self.scheduleAlapCompactionForSubnodes(endCurClk, outputMinUseTimeGetter)

            # check if scheduling was successful to fit all nodes in this clock cycle
            fail = False
            curClkBegin = None
            curClkEnd = None
            for node0 in self._subNodes:
                t = node0.scheduledZero
                if curClkBegin is None:
                    curClkBegin = indexOfClkPeriod(t, clkPeriod) * clkPeriod
                    curClkEnd = curClkBegin + clkPeriod - epsilon
                elif t < curClkBegin or curClkEnd < t:
                    fail = True
                    break

            if not moveToPrevClkTried and fail:
                self.copyScheduling(lastSchedule)
                self.setScheduling(prevSchedule)
                # does not fit in clk where first output is, we move -1 clk
                minClkI -= 1
                moveToPrevClkTried = True

            else:
                if moveToPrevClkTried and fail:
                    self.setScheduling(prevSchedule)
                self.copySchedulingFromChildren()
                self.checkScheduling()

                scheduledZero, scheduledIn, scheduledOut = prevSchedule[self]
                if self.scheduledZero != scheduledZero or self.scheduledIn != scheduledIn or self.scheduledOut != scheduledOut:
                    for dep in self.dependsOn:
                        yield dep.obj
                return
