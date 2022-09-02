from math import inf, ceil

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict


class HlsScheduler():
    """
    A class which executes the scheduling of netlist nodes.
    
    :ivar netlist: The reference on parent HLS netlist context which is this scheduler for.
    :ivar resolution: The time resolution specified in seconds (1e-9 is 1ns). 
    :ivar epsilon: The minimal step of time allowed.
    """
    
    def __init__(self, netlist: "HlsNetlistCtx", resolution: float):
        self.netlist = netlist
        self.resolution = resolution
        self.epsilon = 1
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
            debugPath = UniqList() 
        else:
            # normal run without checking for cycles
            debugPath = None

        for o in self.netlist.iterAllNodes():
            o.scheduleAsap(debugPath)

    def _copyAndResetScheduling(self):
        currentSchedule: SchedulizationDict = {}
        for node in self.netlist.iterAllNodes():
            node:HlsNetNode
            node.copyScheduling(currentSchedule)
            node.resetScheduling()
            
        return currentSchedule
        
    def _scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        normalizedClkPeriod: int = self.netlist.normalizedClkPeriod
        consts = UniqList()
        minTime = inf       
        for node in self.netlist.iterAllNodes():
            if isinstance(node, HlsNetNodeConst):
                consts.append(node)
                continue
            if node.scheduledIn is None:
                node.scheduleAlapCompaction(asapSchedule, None)
            if node.scheduledIn:
                minTime = min(minTime, min(node.scheduledIn))
            if node.scheduledOut:
                minTime = min(minTime, min(node.scheduledOut))
                
        for c in consts:
            # constants are special because they have no inputs and their scheduling purely depends on its use from other nodes
            assert len(c.usedBy) == 1, c
            assert len(c._outputs) == 1, c
            assert not c._inputs, c
            c.scheduledIn = ()
            uses = c.usedBy[0]
            if uses:
                c.scheduledOut = (min(u.obj.scheduledIn[u.in_i] for u in uses),)
            else:
                c.scheduledOut = (0,) 

            minTime = min(minTime, min(node.scheduledOut))

        if minTime < 0:
            # move everything forward in time so there is nothing scheduled in negative time, the move must be aligned to clock boundaries
            offset = ceil(-minTime / normalizedClkPeriod) * normalizedClkPeriod
        elif minTime >= normalizedClkPeriod:
            offset = -(minTime // normalizedClkPeriod) * normalizedClkPeriod 
        else:
            offset = None

        if offset is not None:
            for node in self.netlist.iterAllNodes():
                node: HlsNetNode
                node.moveSchedulingTime(offset)

    def schedule(self):
        self._scheduleAsap()
        self._checkAllNodesScheduled()
        asapSchedule = self._copyAndResetScheduling()
        self._scheduleAlapCompaction(asapSchedule)
        self._checkAllNodesScheduled()
        
