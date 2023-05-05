from collections import deque
from math import inf
from typing import Deque, Set, List

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.scheduler.resourceList import HlsSchedulerResourceUseList


class HlsScheduler():
    """
    A class which executes the scheduling of netlist nodes.

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
        self.debug = True

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
            debugPath = UniqList()
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

    def _normalizeSchedulingTime(self, allNodes: List[HlsNetNode], clkPeriod: int):
        minTime = inf
        for node in self.netlist.iterAllNodes():
            if node.scheduledIn:
                minTime = min(minTime, min(node.scheduledIn))
            if node.scheduledOut:
                minTime = min(minTime, min(node.scheduledOut))
        assert isinstance(minTime, int), minTime
        clkI0 = indexOfClkPeriod(minTime, clkPeriod)
        if clkI0 != 0:
            offset = -clkI0 * clkPeriod
            for node in allNodes:
                node: HlsNetNode
                node.moveSchedulingTime(offset)
            # nodes will move its resoruces to correct slot in resourceUsage
            self.resourceUsage.normalizeOffsetTo0()

    def _scheduleAlapCompaction(self, freezeRightSideOfSchedule: bool):
        """
        Iteratively try to move any node to a later time if dependencies allow it.
        Nodes without outputs are banned from moving.
        """
        allNodes = list(self.netlist.iterAllNodes())
        curMaxInTime = 0
        for node0 in allNodes:
            if node0.scheduledIn:
                curMaxInTime = max(curMaxInTime, max(node0.scheduledIn))
            if not node0.scheduledIn:
                curMaxInTime = max(curMaxInTime, node0.scheduledZero)

        clkPeriod = self.netlist.normalizedClkPeriod
        # + 1 to get end of clk
        endOfLastClk = (indexOfClkPeriod(curMaxInTime, clkPeriod) + 1) * clkPeriod
        if freezeRightSideOfSchedule:
            nodesBannedToMove = set()
            for n in allNodes:
                if isinstance(n, HlsNetNodeWriteBackedge) or not any(n.usedBy):
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
        self._normalizeSchedulingTime(allNodes, clkPeriod)

    def _dbgDumpResources(self):
        clkPeriod = self.netlist.normalizedClkPeriod
        clkOff = self.resourceUsage.clkOffset
        for i, resDict in enumerate(self.resourceUsage):
            print(f"{(i+clkOff) * clkPeriod} to {(i+clkOff + 1) * clkPeriod}")
            for res, cnt in resDict.items():
                print(f"  {res}={cnt:d}")

    def _scheduleAsapCompaction(self):
        """
        Iteratively try to move any node to a sooner time if dependencies allow it.
        Nodes without inputs are moved on the beggining of the clock cycle where they curently are scheduled.
        """
        allNodes = list(self.netlist.iterAllNodes())
        toSearch: Deque[HlsNetNode] = deque(reversed(allNodes))
        toSearchSet: Set[HlsNetNode] = set(allNodes)
        curMinInTime = 0
        for node0 in allNodes:
            if node0.scheduledIn:
                curMinInTime = min(curMinInTime, min(node0.scheduledIn))

        clkPeriod = self.netlist.normalizedClkPeriod
        # + 1 to get end of clk
        startOfFirstClk = indexOfClkPeriod(curMinInTime, clkPeriod) * clkPeriod
        while toSearch:
            node0 = toSearch.popleft()
            toSearchSet.remove(node0)
            # self._checkAllNodesScheduled()
            for node1 in node0.scheduleAsapCompaction(startOfFirstClk, None):
                if node1 not in toSearchSet:
                    toSearch.append(node1)
                    toSearchSet.add(node1)
            # self._checkAllNodesScheduled()
        self._normalizeSchedulingTime(allNodes, clkPeriod)

    def schedule(self):
        self._scheduleAsap()
        self._checkAllNodesScheduled()
        maxTime = max((n.scheduledZero for n in self.netlist.iterAllNodes()), default=0)
        if maxTime > self.netlist.normalizedClkPeriod:
            self._scheduleAlapCompaction(False)
            self._checkAllNodesScheduled()
            self._scheduleAsapCompaction()
            self._checkAllNodesScheduled()
            self._scheduleAlapCompaction(True)
            self._checkAllNodesScheduled()
