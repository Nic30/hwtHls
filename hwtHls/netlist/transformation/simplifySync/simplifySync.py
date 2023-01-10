from io import StringIO
from typing import Set, Optional

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.analysis.syncDependecy import HlsNetlistAnalysisPassSyncDependency
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge, \
    HlsNetNodeReadBackwardEdge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.explicitSyncDataToOrdering import HlsNetlistPassExplicitSyncDataToOrdering
from hwtHls.netlist.transformation.simplifySync.simplifyBackedge import netlistReduceUnusedBackwardEdgeBuffer
from hwtHls.netlist.transformation.simplifySync.simplifyBackedgeStraightening import netlistBackedgeStraightening
from hwtHls.netlist.transformation.simplifySync.simplifyBackedgeWritePropagation import netlistBackedgeWritePropagation
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncConditions, \
    netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistOrderingReduce, netlistTrivialOrderingReduce
from hwtHls.netlist.transformation.simplifySync.simplifySyncIsland import netlistReduceExplicitSyncMergeSuccessorIsland
from hwtHls.netlist.transformation.simplifySync.simplifySyncUtils import netlistContainsExplicitSync


class HlsNetlistPassSimplifySync(HlsNetlistPass):
    """
    Simplify HlsNetNodeExplicitSync instances
    
    :note: this is separated from HlsNetlistPassSimplify because it intensively uses HlsNetlistAnalysisPassSyncDependency
        which is expensive to compute and update.
    """

    def __init__(self, dbgTracer: DebugTracer):
        self._dbgTrace = dbgTracer
        HlsNetlistPass.__init__(self)
        
    def apply(self, hls:"HlsScope", netlist:HlsNetlistCtx,
              parentWorklist: Optional[UniqList[HlsNetNode]]=None,
              parentRemoved: Optional[Set[HlsNetNode]]=None):
        if not netlistContainsExplicitSync(netlist, parentRemoved):
            # nothing to optimize
            return

        # print("HlsNetlistPassSimplifySync.apply")
        threads = HlsNetlistAnalysisPassDataThreads(netlist)
        threads.run(removed=parentRemoved)  

        HlsNetlistPassExplicitSyncDataToOrdering().apply(hls, netlist, parentRemoved=parentRemoved)

        removed: Set[HlsNetNode] = netlist.builder._removedNodes if parentRemoved is None else parentRemoved
        syncDeps = HlsNetlistAnalysisPassSyncDependency(netlist, removed=removed)
        netlist._analysis_cache[HlsNetlistAnalysisPassSyncDependency] = syncDeps
        HlsNetlistPassConsystencyCheck.checkRemovedNotReachable(netlist, removed)
        syncDeps.run()
        
        worklist: UniqList[HlsNetNode] = UniqList(
            n for n in netlist.iterAllNodes()
            if isinstance(n, (HlsNetNodeExplicitSync, HlsNetNodeReadSync)))
        syncIslandOptimized: Set[HlsNetNodeExplicitSync] = set()
        dbgTrace = self._dbgTrace
        try:
            netlist.setupNetlistListeners(syncDeps._beforeNodeAddedListener, syncDeps._beforeInputDriveUpdate, removed)
            worklistTmp = []
            while worklist:
                n = worklist.pop()
                if n in removed:
                    continue
                # print("HlsNetlistPassSimplifySync", n)
                
                if isinstance(n, HlsNetNodeExplicitSync):
                    n: HlsNetNodeExplicitSync
                    if netlistReduceExplicitSyncConditions(dbgTrace, n, worklistTmp, removed) and n in removed:
                        HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                        pass
                    elif netlistTrivialOrderingReduce(n, worklistTmp, removed):
                        pass
                    else:
                        # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                        # netlistOrderingReduce(n, threads)
                        HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
    
                        if isinstance(n, HlsNetNodeRead):
                            if isinstance(n, HlsNetNodeReadBackwardEdge) and netlistReduceUnusedBackwardEdgeBuffer(dbgTrace, n, worklistTmp, removed):
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                                pass
                            elif n not in syncIslandOptimized and netlistReduceExplicitSyncMergeSuccessorIsland(dbgTrace, n, worklistTmp, removed, syncDeps, threads, syncIslandOptimized):
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                                pass
                            
                        elif n.__class__ is HlsNetNodeExplicitSync:
                            if netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite(dbgTrace, n, worklistTmp, removed, syncDeps):
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                            elif n not in syncIslandOptimized and netlistReduceExplicitSyncMergeSuccessorIsland(dbgTrace, n, worklistTmp, removed, syncDeps, threads, syncIslandOptimized):
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
         
                        elif isinstance(n, HlsNetNodeWriteBackwardEdge):
                            HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)
                            if netlistBackedgeWritePropagation(dbgTrace, n, worklistTmp, removed, syncDeps):
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)
                            elif netlistBackedgeStraightening(dbgTrace, n, worklistTmp, removed, syncDeps):
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)
                else:
                    assert not isinstance(n, HlsNetNodeReadSync), (n, "Should be already removed")
                
                if worklistTmp:
                    for tmp in worklistTmp:
                        if not isinstance(tmp, HlsNetNode):
                            raise AssertionError(tmp)
                    syncIslandOptimized.clear()
                    worklist.extend(worklistTmp)
                    if parentWorklist is not None:
                        parentWorklist.extend(worklistTmp)
                    worklistTmp.clear()
    
            if parentRemoved is None:
                # filter nodes only if not done by the parent
                netlist.filterNodesUsingSet(removed)            
    
        finally:
            netlist.dropNetlistListeners()
