from typing import Set, Optional

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.consistencyCheck import HlsNetlistPassConsistencyCheck
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.simplifyBackedge import netlistReduceUnusedBackedgeBuffer
from hwtHls.netlist.transformation.simplifySync.simplifyBackedgeStraightening import netlistBackedgeStraightening
from hwtHls.netlist.transformation.simplifySync.simplifyChannelValPropagationForNeverWritten import simplifyChannelValPropagationForNeverWritten
from hwtHls.netlist.transformation.simplifySync.simplifyEdgeWritePropagation import netlistEdgeWritePropagation, \
    netlistEdgeWriteVoidWithoudDeps
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistOrderingReduce, netlistTrivialOrderingReduce
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


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
              parentWorklist: Optional[SetList[HlsNetNode]]=None) -> PreservedAnalysisSet:
        dbgTrace = self._dbgTrace
        with dbgTrace.scoped(HlsNetlistPassSimplifySync, None):
            dbgEn = dbgTrace._out is not None
            if dbgEn:
                HlsNetlistPassConsistencyCheck.checkRemovedNotReachable(netlist)

            # assert netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassReachability) is None
            reachDb: HlsNetlistAnalysisPassReachability = netlist.getAnalysis(HlsNetlistAnalysisPassReachability)

            worklist: SetList[HlsNetNode] = SetList(
                n for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.POSTORDER)
                if isinstance(n, (HlsNetNodeExplicitSync, HlsNetNodeReadSync))
            )

            try:
                reachDb._installNetlistListeners(netlist)

                worklistTmp = []
                while worklist:
                    n = worklist.pop()
                    if n._isMarkedRemoved:
                        continue

                    elif isinstance(n, HlsNetNodeExplicitSync):
                        n: HlsNetNodeExplicitSync
                        if netlistReduceExplicitSyncFlags(dbgTrace, n, worklistTmp) and n._isMarkedRemoved:
                            if dbgEn:
                                HlsNetlistPassConsistencyCheck().runOnHlsNetlist(n.netlist)
                            pass
                        elif netlistTrivialOrderingReduce(n, worklistTmp):
                            pass
                        else:
                            # if dbgEn:
                            #   HlsNetlistPassConsistencyCheck().runOnHlsNetlist(n.netlist, removed=removed)
                            netlistOrderingReduce(dbgTrace, n, reachDb)
                            if dbgEn:
                                HlsNetlistPassConsistencyCheck().runOnHlsNetlist(n.netlist)

                            assert n.__class__ is not HlsNetNodeExplicitSync, (n, "Nodes of this type should not exist at this stage")

                            if isinstance(n, HlsNetNodeRead):
                                if isinstance(n, HlsNetNodeReadBackedge):
                                    if netlistReduceUnusedBackedgeBuffer(dbgTrace, n, worklistTmp):
                                        if dbgEn:
                                            HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)
                                            # HlsNetlistPassConsistencyCheck().runOnHlsNetlist(n.netlist, removed=removed)

                            elif isinstance(n, HlsNetNodeWrite) and n.associatedRead is not None:
                                isBackedge = isinstance(n, HlsNetNodeWriteBackedge)
                                if simplifyChannelValPropagationForNeverWritten(dbgTrace, n, worklistTmp):
                                    pass
                                elif netlistEdgeWritePropagation(dbgTrace, n, worklistTmp):
                                    if dbgEn:
                                        HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)
                                        HlsNetlistPassConsistencyCheck._checkSyncNodes(netlist)

                                elif isBackedge and  netlistBackedgeStraightening(dbgTrace, n, worklistTmp, reachDb):
                                    if dbgEn:
                                        HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)
                                        HlsNetlistPassConsistencyCheck._checkSyncNodes(netlist)
                                elif netlistEdgeWriteVoidWithoudDeps(dbgTrace, n, worklistTmp):
                                    if dbgEn:
                                        HlsNetlistPassConsistencyCheck._checkCycleFree(n.netlist)
                                        HlsNetlistPassConsistencyCheck._checkSyncNodes(netlist)

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

                if parentWorklist is None:
                    # filter nodes only if not done by the parent
                    netlist.filterNodesUsingRemovedSet(recursive=True)

            finally:
                netlist.dropNetlistListeners()
                netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability)

            return PreservedAnalysisSet()
