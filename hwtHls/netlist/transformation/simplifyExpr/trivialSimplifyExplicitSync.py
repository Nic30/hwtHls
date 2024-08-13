from typing import Set

from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassTrivialSimplifyExplicitSync(HlsNetlistPass):

    def __init__(self, dbgTracer: DebugTracer):
        self.dbgTracer = dbgTracer

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        dbgTracer = self.dbgTracer
        removed: Set[HlsNetNode] = netlist.builder._removedNodes
        for n in netlist.iterAllNodes():
            if isinstance(n, HlsNetNodeExplicitSync) and n not in removed:
                netlistReduceExplicitSyncFlags(dbgTracer, n, None, removed)
        if removed:
            netlist.filterNodesUsingSet(removed)
            return PreservedAnalysisSet.preserveReachablity()
        else:
            return PreservedAnalysisSet.preserveAll()