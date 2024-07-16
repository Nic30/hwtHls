from collections import deque
from io import StringIO
from itertools import chain
from math import inf, isfinite
import sys
from typing import Deque, Set, List, Optional, Callable

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, beginOfClk, \
    beginOfClkWindow, beginOfNextClk
from hwtHls.netlist.scheduler.resourceList import HlsSchedulerResourceUseList


def asapSchedulePartlyScheduled(o: HlsNetNodeOut,
                                beforeSchedulingFn: Optional[Callable[[HlsNetNode], bool]],
                                beginOfFirstClk:int=0) -> List[HlsNetNode]:
    """
    Run ASAP scheduling partly scheduled netlist.

    :param beforeSchedulingFn: a function which can be used to initialize or skip node which is going to be scheduled
    """
    newlyScheduledNodes: List[HlsNetNode] = []
    n = o.obj
    if n.scheduledIn is None:
        if beforeSchedulingFn is not None and not beforeSchedulingFn(n):
            return newlyScheduledNodes
        # add all not scheduled nodes to elmTimeSlot
        toSearch = [n]
        seen = set()
        while toSearch:
            n1 = toSearch.pop()
            if n1 not in seen and n1.scheduledIn is None:
                if beforeSchedulingFn is not None and not beforeSchedulingFn(n1):
                    continue
                newlyScheduledNodes.append(n1)
                seen.add(n1)
                for dep in n1.dependsOn:
                    toSearch.append(dep.obj)

        n.scheduleAsap(None, beginOfFirstClk, None)

    return newlyScheduledNodes


class HlsScheduler():
    """
    A class which executes the scheduling of netlist nodes.
    Scheduling itself is performed by methods of :class:`HlsNetNode` (:class:`SchedulableNode`) and the result is stored in its instances.

    :note: :class:`HlsNetNode` can customize how it is scheduled. Which is often required to implement special hardblock/io/memory properties.

    :ivar netlist: The reference on parent HLS netlist context which is this scheduler for.
    :ivar resolution: The time resolution specified in seconds (1e-9 is 1ns).
    :ivar epsilon: The minimal step of time allowed.
    :ivar resourceUsage: resource usage list used for list scheduling algorithm, (resource available is stored in node which is using this list)
    """

    def __init__(self, netlist: "HlsNetlistCtx", resolution: float):
        self.netlist = netlist
        self.resolution = resolution
        self.epsilon = 1
        self.resourceUsage = HlsSchedulerResourceUseList()
        self.debug = False

    def _checkAllNodesScheduled(self):
        """
        Check that all nodes do have some time resolved by scheduler.
        """
        for node in self.netlist.iterAllNodes():
            node.checkScheduling()

    def _scheduleAsap(self):
        """
        As Soon As Possible scheduler
        * The graph must not contain cycles.
        * DFS from outputs, decorate nodes with scheduledIn,scheduledOut time.
        """
        if self.debug:
            # debug run which will raise an exception containing cycle node ids
            debugPath = SetList()
        else:
            # normal run without checking for cycles
            debugPath = None

        for o in self.netlist.iterAllNodes():
            o.scheduleAsap(debugPath, 0, None)

    def _copyAndResetScheduling(self):
        currentSchedule: SchedulizationDict = {}
        for node in self.netlist.iterAllNodes():
            node:HlsNetNode
            node.copyScheduling(currentSchedule)
            node.resetScheduling()

        return currentSchedule

    def getSchedulingMinTime(self, clkPeriod: SchedTime):
        minTime = inf
        for node in self.netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if node.scheduledIn:
                minTime = min(minTime, min(node.scheduledIn))
            if node.scheduledOut:
                minTime = min(minTime, min(node.scheduledOut))
        if not isfinite(minTime):
            minTime = 0
        clkI0 = indexOfClkPeriod(minTime, clkPeriod)
        return minTime, clkI0

    def moveSchedulingTime(self, clkOffset: int, clkPeriod: SchedTime):
        offset = clkOffset * clkPeriod
        for node in self.netlist.iterAllNodes():
            node: HlsNetNode
            node.moveSchedulingTime(offset)
        # nodes will move its resources to correct slot in resourceUsage
        self.resourceUsage.normalizeOffsetTo0()

    def normalizeSchedulingTime(self, clkPeriod: SchedTime):
        """
        Move schedule of all nodes to make circuit start at clock window 0.
        
        :note: Schedule times may be negative or all may be somewhere after clock window 0. 
        """
        _, clkI0 = self.getSchedulingMinTime(clkPeriod)
        if clkI0 != 0:
            self.moveSchedulingTime(-clkI0, clkPeriod)

    def _scheduleAlapCompaction(self, freezeRightSideOfSchedule: bool):
        """
        Iteratively try to move any node to a later time if dependencies allow it.
        Nodes without outputs are banned from moving.
        """
        curMaxInTime = -inf
        netlist = self.netlist
        for node0 in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            curMaxInTime = max(curMaxInTime, node0.scheduledZero)
        if not isfinite(curMaxInTime):
            curMaxInTime = 0

        clkPeriod = netlist.normalizedClkPeriod
        endOfLastClk = beginOfNextClk(curMaxInTime, clkPeriod)
        allNodes = list(netlist.iterAllNodes())
        if freezeRightSideOfSchedule:
            nodesBannedToMove = set()
            for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
                if isinstance(n, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)) or not any(n.usedBy):
                    nodesBannedToMove.add(n)
            toSearch: Deque[HlsNetNode] = deque(n for n in reversed(allNodes) if n not in nodesBannedToMove)
        else:
            nodesBannedToMove = None
            toSearch: Deque[HlsNetNode] = deque(reversed(allNodes))

        toSearchSet: Set[HlsNetNode] = set(toSearch)
        # perform compaction while scheduling changes
        while toSearch:
            node0 = toSearch.popleft()
            toSearchSet.remove(node0)
            for node1 in node0.scheduleAlapCompaction(endOfLastClk, None):
                if node1 not in toSearchSet and (nodesBannedToMove is None or node1 not in nodesBannedToMove):
                    toSearch.append(node1)
                    toSearchSet.add(node1)

    def _scheduleAsapCompaction(self):
        """
        Iteratively try to move any node to a sooner time if dependencies allow it.
        Nodes without inputs are moved on the beginning of the clock cycle where they currently are scheduled.
        """
        netlist = self.netlist
        allNodes = list(netlist.iterAllNodes())
        toSearch: Deque[HlsNetNode] = deque(reversed(allNodes))
        toSearchSet: Set[HlsNetNode] = set(allNodes)
        _, firstClkI = self.getSchedulingMinTime(netlist.normalizedClkPeriod)
        startOfFirstClk = beginOfClkWindow(firstClkI, netlist.normalizedClkPeriod)
        while toSearch:
            node0 = toSearch.popleft()
            toSearchSet.remove(node0)
            # self._checkAllNodesScheduled()
            for node1 in node0.scheduleAsapCompaction(startOfFirstClk, None):
                if node1 not in toSearchSet:
                    toSearch.append(node1)
                    toSearchSet.add(node1)
            # self._checkAllNodesScheduled()

    def _scheduleIsMulticlock(self):
        clkPeriod = self.netlist.normalizedClkPeriod
        curBegin = None
        curEnd = None
        for n in self.netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            for t in chain(n.scheduledIn, n.scheduledOut):
                if curBegin is None:
                    # compute boundaries of clock window
                    curBegin = beginOfClk(t, clkPeriod)
                    curEnd = curBegin + clkPeriod
                else:
                    # compare if time is in current clock window
                    if t < curBegin or t >= curEnd:
                        return True
        return False

    def schedule(self):
        dbgDir = self.netlist.platform._debug.dir
        if dbgDir:
            from hwtHls.netlist.translation.dumpSchedulingJson import HlsNetlistAnalysisPassDumpSchedulingJson
            from hwtHls.platform.fileUtils import outputFileGetter

        self._scheduleAsap()
        self._checkAllNodesScheduled()

        if self.debug and dbgDir is not None:
            HlsNetlistAnalysisPassDumpSchedulingJson(outputFileGetter(dbgDir, "schedulingDbg.0.asap0.hwschedule.json"),
                                             expandCompositeNodes=True).runOnHlsNetlist(self.netlist)

        if self._scheduleIsMulticlock():
            # if circuit schedule spans over multiple clock periods
            self._scheduleAlapCompaction(False)
            if self.debug:
                self._checkAllNodesScheduled()
                if dbgDir is not None:
                    HlsNetlistAnalysisPassDumpSchedulingJson(outputFileGetter(dbgDir, "schedulingDbg.1.alap0.hwschedule.json"),
                                                     expandCompositeNodes=True).runOnHlsNetlist(self.netlist)

            self._scheduleAsapCompaction()
            if self.debug:
                self._checkAllNodesScheduled()
                if dbgDir is not None:
                    HlsNetlistAnalysisPassDumpSchedulingJson(outputFileGetter(dbgDir, "schedulingDbg.2.asap1.hwschedule.json"),
                                                     expandCompositeNodes=True).runOnHlsNetlist(self.netlist)

            self._scheduleAlapCompaction(True)
            if self.debug:
                self._checkAllNodesScheduled()
                if dbgDir is not None:
                    HlsNetlistAnalysisPassDumpSchedulingJson(outputFileGetter(dbgDir, "schedulingDbg.3.alap1.hwschedule.json"),
                                                     expandCompositeNodes=True).runOnHlsNetlist(self.netlist)

    def _dbgDumpResources(self, out:StringIO=sys.stdout):
        clkPeriod = self.netlist.normalizedClkPeriod
        clkOff = self.resourceUsage.clkOffset
        for i, resDict in enumerate(self.resourceUsage):
            out.write(f"{(i+clkOff) * clkPeriod} to {(i+clkOff + 1) * clkPeriod}\n")
            for res, cnt in resDict.items():
                out.write(f"  {res}={cnt:d}\n")
