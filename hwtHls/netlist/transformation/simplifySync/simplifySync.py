from typing import Set, Optional

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.simplifyBackedge import netlistReduceUnusedBackedgeBuffer
from hwtHls.netlist.transformation.simplifySync.simplifyBackedgeStraightening import netlistBackedgeStraightening
from hwtHls.netlist.transformation.simplifySync.simplifyEdgeWritePropagation import netlistEdgeWritePropagation, \
    netlistEdgeWriteVoidWithoudDeps
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags, \
    netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistOrderingReduce, netlistTrivialOrderingReduce
from hwtHls.netlist.transformation.simplifySync.simplifySyncIsland import netlistReduceExplicitSyncDissolve
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwt.pyUtils.typingFuture import override


class HlsNetlistPassSimplifySync(HlsNetlistPass):
    """
    Simplify HlsNetNodeExplicitSync instances

    :note: this is separated from HlsNetlistPassSimplify because it intensively uses HlsNetlistAnalysisPassReachability
        which is expensive to compute and update.
    """

    def __init__(self, dbgTracer: DebugTracer):
        self._dbgTrace = dbgTracer
        HlsNetlistPass.__init__(self)

    @override
    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx,
              parentWorklist: Optional[SetList[HlsNetNode]]=None,
              parentRemoved: Optional[Set[HlsNetNode]]=None):
        dbgTrace = self._dbgTrace
        with dbgTrace.scoped(HlsNetlistPassSimplifySync, None):
            dbgEn = dbgTrace._out is not None
            removed: Set[HlsNetNode] = netlist.builder._removedNodes if parentRemoved is None else parentRemoved
            if dbgEn:
                HlsNetlistPassConsystencyCheck.checkRemovedNotReachable(netlist, removed)

            assert netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassReachability) is None
            reachDb: HlsNetlistAnalysisPassReachability = netlist.getAnalysis(HlsNetlistAnalysisPassReachability(removed=removed))

            worklist: SetList[HlsNetNode] = SetList(
                n for n in netlist.iterAllNodes()
                if isinstance(n, (HlsNetNodeExplicitSync, HlsNetNodeReadSync, HlsNetNodeIoClusterCore))
            )

            try:
                netlist.setupNetlistListeners(reachDb._beforeNodeAddedListener,
                                              reachDb._beforeInputDriveUpdate,
                                              reachDb._beforeOutputUpdate, removed)

                worklistTmp = []
                while worklist:
                    n = worklist.pop()
                    if n in removed:
                        continue

                    elif isinstance(n, HlsNetNodeExplicitSync):
                        n: HlsNetNodeExplicitSync
                        if netlistReduceExplicitSyncFlags(dbgTrace, n, worklistTmp, removed) and n in removed:
                            if dbgEn:
                                HlsNetlistPassConsystencyCheck().runOnHlsNetlist(n.netlist, removed=removed)
                            pass
                        elif netlistTrivialOrderingReduce(n, worklistTmp, removed):
                            pass
                        else:
                            # if dbgEn:
                            #   HlsNetlistPassConsystencyCheck().runOnHlsNetlist(n.netlist, removed=removed)
                            netlistOrderingReduce(dbgTrace, n, reachDb)
                            if dbgEn:
                                HlsNetlistPassConsystencyCheck().runOnHlsNetlist(n.netlist, removed=removed)

                            assert n.__class__ is not HlsNetNodeExplicitSync, (n, "Nodes of this type should not exist at this stage")

                            if isinstance(n, HlsNetNodeRead):
                                if isinstance(n, HlsNetNodeReadBackedge):
                                    if netlistReduceUnusedBackedgeBuffer(dbgTrace, n, worklistTmp, removed):
                                        if dbgEn:
                                            HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                            # HlsNetlistPassConsystencyCheck().runOnHlsNetlist(n.netlist, removed=removed)

                            elif isinstance(n, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)):
                                if netlistEdgeWritePropagation(dbgTrace, n, worklistTmp, removed, reachDb):
                                    if dbgEn:
                                        HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                        HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)

                                elif netlistBackedgeStraightening(dbgTrace, n, worklistTmp, removed, reachDb):
                                    if dbgEn:
                                        HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                        HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)
                                elif netlistEdgeWriteVoidWithoudDeps(dbgTrace, n, worklistTmp, removed):
                                    if dbgEn:
                                        HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                                        HlsNetlistPassConsystencyCheck._checkSyncNodes(netlist, removed)
                                    
                    else:
                        assert not isinstance(n, HlsNetNodeReadSync), (n, "Should be already removed")

                    if worklistTmp:
                        # copy worklist to parent worklist and store only nodes with sync to local worklist
                        if parentWorklist is not None:
                            parentWorklist.extend(worklistTmp)

                        for n in worklistTmp:
                            if isinstance(n, HlsNetNodeExplicitSync):
                                worklist.append(n)
                            else:
                                assert isinstance(n, HlsNetNode), n

                        worklistTmp.clear()

                if parentRemoved is None:
                    # filter nodes only if not done by the parent
                    netlist.filterNodesUsingSet(removed)

            finally:
                netlist.dropNetlistListeners()
                netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability)
