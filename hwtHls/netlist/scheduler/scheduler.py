from collections import deque
from itertools import islice
from math import ceil, inf
from typing import Deque, Set, List, Dict

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod


class HlsSchedulerResourceUseList(List[Dict[object, int]]):
    """
    A list of dictionaries with resource usage info which automatically extends itself on both sides.
    The index in this list is an index of the clock period.
    This index can be negative as circuit may be temporarly scheduled to negative times (e.g. in ALAP).

    :note: This is used for list scheduling greedy algorithm to track how many resources were used in individual clock cycle windows.
    """

    def __init__(self):
        list.__init__(self)
        self.clkOffset = 0  # item 0 corresponds to clock period 0

    def getUseCount(self, resourceType, clkI: int) -> int:
        return self[clkI].get(resourceType, 0)
    
    def addUse(self, resourceType, clkI: int):
        cur = self[clkI]
        cur[resourceType] = cur.get(resourceType, 0) + 1 

    def removeUse(self, resourceType, clkI: int):
        i = self.clkOffset + clkI
        assert i >= 0, (i, clkI, resourceType, "Trying to remove from clock where no resource is used")
        cur = list.__getitem__(self, i)
        curCnt = cur[resourceType]
        if curCnt == 1:
            cur.pop(resourceType)
        else:
            assert curCnt > 0, (clkI, resourceType, "Resource must be used in order to remove the use")
            cur[resourceType] = curCnt - 1
        
    def moveUse(self, resourceType, fromClkI: int, toClkI: int):
        # accessing directly to raise index error if there is not yet any use in this clk
        cur = list.__getitem__(self, self.clkOffset + fromClkI)
        try:
            curCnt = cur[resourceType]
        except KeyError:
            raise AssertionError("Trying to move usage which is not present", resourceType, fromClkI, toClkI)

        assert curCnt > 0, (resourceType, curCnt)
        if curCnt == 1:
            cur.pop(resourceType)
        else:
            cur[resourceType] = curCnt - 1
        
        to = self[toClkI]
        toCnt = to.get(resourceType, 0)
        to[resourceType] = toCnt + 1

    def findFirstClkISatisfyingLimit(self, resourceType, beginClkI: int, limit: int) -> int:
        """
        The first 
        """
        assert limit > 0, limit
        clkI = beginClkI
        while True:
            res = self[clkI]
            if res.get(resourceType, 0) < limit:
                return clkI
            clkI += 1

    def findFirstClkISatisfyingLimitEndToStart(self, resourceType, endClkI: int, limit: int) -> int:
        """
        :attention: Limit for first clk period where search is increased because it is expected that the requested
            resource is already allocated there.
        """
        assert limit > 0, limit
        clkI = endClkI
        clkIFirst = clkI
        while True:
            res = self[clkI]
            if res.get(resourceType, 0) < (limit + 1 if clkI == clkIFirst else limit):
                return clkI
            clkI -= 1
   
    def __getitem__(self, i: int):
        i += self.clkOffset
        if i < 0:
            self[:0] = [{} for _ in range(-i)]
            self.clkOffset -= -i 
            i = 0

        try:
            return list.__getitem__(self, i)
        except IndexError:
            assert i >= 0, i
            for _ in range(i + 1 - len(self)):
                self.append({})
            return self[len(self) - 1]


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
        
    def _scheduleAlapCompaction(self):  # , asapSchedule: SchedulizationDict
        """
        Iteratively try to move any node to a later time if dependencies allow it.
        Nodes without outputs are banned from moving.
        """
        allNodes = list(self.netlist.iterAllNodes())
        toSearch: Deque[HlsNetNode] = deque(reversed(allNodes))
        toSearchSet: Set[HlsNetNode] = set(allNodes)
        curMaxInTime = 0
        for node0 in allNodes:
            if node0.scheduledIn:
                curMaxInTime = max(curMaxInTime, max(node0.scheduledIn))
        clkPeriod = self.netlist.normalizedClkPeriod
        # + 1 to get end of clk
        endOfLastClk = (indexOfClkPeriod(curMaxInTime, clkPeriod) + 1) * clkPeriod 
        while toSearch:
            node0 = toSearch.popleft()
            toSearchSet.remove(node0)
            for node1 in node0.scheduleAlapCompaction(endOfLastClk, None):
                if node1 not in toSearchSet:
                    toSearch.append(node1)
                    toSearchSet.add(node1)
        
        # consts = UniqList()
        # minTime = inf       
        # for node in self.netlist.iterAllNodes():
        #    if isinstance(node, HlsNetNodeConst):
        #        consts.append(node)
        #        continue
        #    if node.scheduledIn is None:
        #        node.scheduleAlapCompaction(asapSchedule, None)
        #    if node.scheduledIn:
        #        minTime = min(minTime, min(node.scheduledIn))
        #    if node.scheduledOut:
        #        minTime = min(minTime, min(node.scheduledOut))
        #        
        # for c in consts:
        #    # constants are special because they have no inputs and their scheduling purely depends on its use from other nodes
        #    assert len(c.usedBy) == 1, c
        #    assert len(c._outputs) == 1, c
        #    assert not c._inputs, c
        #    c.scheduledIn = ()
        #    uses = c.usedBy[0]
        #    if uses:
        #        c.scheduledOut = (min(u.obj.scheduledIn[u.in_i] for u in uses),)
        #    else:
        #        c.scheduledOut = (0,) 
        #
        #    minTime = min(minTime, min(node.scheduledOut))
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
        
    def schedule(self):
        try:
            self._scheduleAsap()
            self._checkAllNodesScheduled()
            maxTime = max((n.scheduledZero for n in self.netlist.iterAllNodes()), default=0)
            if maxTime > self.netlist.normalizedClkPeriod:
                self._scheduleAlapCompaction()
                self._checkAllNodesScheduled()
        except AssertionError:
            if self.debug:
                from hwtHls.netlist.translation.toTimeline import HlsNetlistPassShowTimeline
                from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
                sch = HlsNetlistAnalysisPassRunScheduler(self.netlist)
                self.netlist._analysis_cache[HlsNetlistAnalysisPassRunScheduler] = sch
                HlsNetlistPassShowTimeline(outputFileGetter("tmp", ".13.schedule.error.html"),
                                           expandCompositeNodes=False).apply(None, self.netlist)
            raise
        
