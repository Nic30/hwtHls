from io import StringIO
from typing import Set, Optional

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge, \
    HlsNetNodeReadBackwardEdge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.ioClusterOutputToInput import netlistReduceIoClusterCoreOutputToInput
from hwtHls.netlist.transformation.simplifySync.simplifyBackedge import netlistReduceUnusedBackwardEdgeBuffer
from hwtHls.netlist.transformation.simplifySync.simplifyBackedgeStraightening import netlistBackedgeStraightening
from hwtHls.netlist.transformation.simplifySync.simplifyBackedgeWritePropagation import netlistBackedgeWritePropagation
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncConditions, \
    netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistOrderingReduce, netlistTrivialOrderingReduce
from hwtHls.netlist.transformation.simplifySync.simplifySyncIsland import netlistReduceExplicitSyncMergeSuccessorIsland


class HlsNetlistPassSimplifySync(HlsNetlistPass):
    """
    Simplify HlsNetNodeExplicitSync instances
    
    :note: this is separated from HlsNetlistPassSimplify because it intensively uses HlsNetlistAnalysisPassReachabilility
        which is expensive to compute and update.
    """

    def __init__(self, dbgTracer: DebugTracer):
        self._dbgTrace = dbgTracer
        HlsNetlistPass.__init__(self)
        
    def apply(self, hls:"HlsScope", netlist:HlsNetlistCtx,
              parentWorklist: Optional[UniqList[HlsNetNode]]=None,
              parentRemoved: Optional[Set[HlsNetNode]]=None):
        dbgTrace = self._dbgTrace
        with dbgTrace.scoped(HlsNetlistPassSimplifySync, None):
            dbgEn = dbgTrace._out is not None
            threads = HlsNetlistAnalysisPassDataThreads(netlist)
            threads.run(removed=parentRemoved)  
    
            removed: Set[HlsNetNode] = netlist.builder._removedNodes if parentRemoved is None else parentRemoved
            reachDb = HlsNetlistAnalysisPassReachabilility(netlist, removed=removed)
            netlist._analysis_cache[HlsNetlistAnalysisPassReachabilility] = reachDb
            if dbgEn:
                HlsNetlistPassConsystencyCheck.checkRemovedNotReachable(netlist, removed)
            reachDb.run()
            
            worklist: UniqList[HlsNetNode] = UniqList(
                n for n in netlist.iterAllNodes()
                if isinstance(n, (HlsNetNodeExplicitSync, HlsNetNodeReadSync, HlsNetNodeIoClusterCore)))
            try:
                netlist.setupNetlistListeners(reachDb._beforeNodeAddedListener, reachDb._beforeInputDriveUpdate, removed)
                worklistTmp = []
                while worklist:
                    n = worklist.pop()
                    if n in removed:
                        continue
                    
                    if isinstance(n, HlsNetNodeExplicitSync):
                        n: HlsNetNodeExplicitSync
                        if netlistReduceExplicitSyncConditions(dbgTrace, n, worklistTmp, removed) and n in removed:
                            if dbgEn:
                                HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                            pass
                        elif netlistTrivialOrderingReduce(n, worklistTmp, removed):
                            pass
                        else:
                            # if dbgEn:
                            #   HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                            netlistOrderingReduce(dbgTrace, n, reachDb)
                            if dbgEn:
                                HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
        
                            if isinstance(n, HlsNetNodeRead):
                                if isinstance(n, HlsNetNodeReadBackwardEdge) and netlistReduceUnusedBackwardEdgeBuffer(dbgTrace, n, worklistTmp, removed):
                                    HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                    # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                                    pass
                                
                            elif n.__class__ is HlsNetNodeExplicitSync:
                                if netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite(dbgTrace, n, worklistTmp, removed, reachDb):
                                    if dbgEn:
                                        HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                        # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
    
                            elif isinstance(n, HlsNetNodeWriteBackwardEdge):
                                if dbgEn:
                                    HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)
                                if netlistBackedgeWritePropagation(dbgTrace, n, worklistTmp, removed, reachDb):
                                    if dbgEn:
                                        HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                        HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)
                                elif netlistBackedgeStraightening(dbgTrace, n, worklistTmp, removed, reachDb):
                                    if dbgEn:
                                        HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                        HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)

                    elif isinstance(n, HlsNetNodeIoClusterCore):
                        if netlistReduceExplicitSyncMergeSuccessorIsland(dbgTrace, n, worklistTmp, removed, reachDb, threads):
                            if dbgEn:
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                        elif netlistReduceIoClusterCoreOutputToInput(dbgTrace, n, worklistTmp, removed, reachDb):
                            if dbgEn:
                                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                # HlsNetlistPassConsystencyCheck().apply(None, n.netlist, removed=removed)
                    else:
                        assert not isinstance(n, HlsNetNodeReadSync), (n, "Should be already removed")
                    
                    if worklistTmp:
                        for tmp in worklistTmp:
                            if not isinstance(tmp, HlsNetNode):
                                raise AssertionError(tmp)
                        worklist.extend(worklistTmp)
                        if parentWorklist is not None:
                            parentWorklist.extend(worklistTmp)
                        worklistTmp.clear()
        
                if parentRemoved is None:
                    # filter nodes only if not done by the parent
                    netlist.filterNodesUsingSet(removed)            
        
            finally:
                netlist.dropNetlistListeners()
