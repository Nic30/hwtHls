from math import inf, ceil

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.loopHeader import HlsLoopGate
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict


class HlsScheduler():
    """
    A class which executes the scheduling of netlist nodes.
    
    :ivar parentHls: The reference on parent HLS context which is this scheduler for.
    :ivar resolution: The time resolution specified in seconds (1e-9 is 1ns). 
    :ivar epsilon: The minimal step of time allowed.
    """
    
    def __init__(self, parentHls: "HlsPipeline", resolution):
        self.parentHls = parentHls
        self.resolution = resolution
        self.epsilon = 1

    def _checkAllNodesScheduled(self):
        """
        Check that all nodes do have some time resolved by scheduler.
        """
        for node in self.parentHls.iterAllNodes():
            assert node.scheduledIn is not None, node
            assert node.scheduledOut is not None, node
            for i, iT, dep in zip(node._inputs, node.scheduledIn, node.dependsOn):
                assert isinstance(iT, int), (i, iT)
                oT = dep.obj.scheduledOut[dep.out_i]
                assert isinstance(oT, int), (dep, oT)
                assert iT >= oT, (dep, i, oT, iT)

    def _scheduleAsap(self):
        """
        As Soon As Possible scheduler
        * The graph must not contain cycles.
        * DFS from outputs, decorate nodes with scheduledIn,scheduledOut time.
        """
        try:
            # normal run without checking for cycles
            for o in self.parentHls.iterAllNodes():
                o.scheduleAsap(None)
            return
        except RecursionError:
            pass
    
        # debug run which will raise an exception containing cycle node ids
        debugPath = UniqList()
        for o in self.parentHls.iterAllNodes():
            o.scheduleAsap(debugPath)

    def _copyAndResetScheduling(self):
        currentSchedule: SchedulizationDict = {}
        for node in self.parentHls.iterAllNodes():
            node:HlsNetNode
            node.copyScheduling(currentSchedule)
            node.resetScheduling()
            
        return currentSchedule
        
    def _scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        normalizedClkPeriod: int = self.parentHls.normalizedClkPeriod
        for node in self.parentHls.iterAllNodes():
            if not node.usedBy or not any(node.usedBy):
                # if it is terminator move to end of clk period
                if isinstance(node, HlsLoopGate):
                    node.scheduledIn, node.scheduledOut = asapSchedule[node] 
        consts = UniqList()
        minTime = inf       
        for node in self.parentHls.iterAllNodes():
            if isinstance(node, HlsNetNodeConst):
                consts.append(node)
                continue
            if node.scheduledIn is None:
                node.scheduleAlapCompaction(asapSchedule)
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
            c.scheduledOut = (min(u.obj.scheduledIn[u.in_i] for u in c.usedBy[0]),)
            if node.scheduledOut:
                minTime = min(minTime, min(node.scheduledOut))
        if minTime < 0:
            offset = -ceil(minTime / normalizedClkPeriod) * normalizedClkPeriod
        elif minTime >= normalizedClkPeriod:
            offset = -(minTime // normalizedClkPeriod) * normalizedClkPeriod 
        else:
            offset = None
        if offset is not None:
            for node in self.parentHls.iterAllNodes():
                node.scheduledIn = tuple(max(t + offset, 0) for t in node.scheduledIn)
                node.scheduledOut = tuple(max(t + offset, 0) for t in node.scheduledOut)

    def schedule(self):
        self._scheduleAsap()
        self._checkAllNodesScheduled()
        asapSchedule = self._copyAndResetScheduling()
        self._scheduleAlapCompaction(asapSchedule)
        self._checkAllNodesScheduled()
        
