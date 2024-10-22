from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import iterAllHierachies


class HlsNetlistPassTrivialSimplifyExplicitSync(HlsNetlistPass):

    def __init__(self, dbgTracer: DebugTracer):
        self.dbgTracer = dbgTracer

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        dbgTracer = self.dbgTracer
        changed = False
        for parent in iterAllHierachies(netlist):
            for n in parent.subNodes:
                if isinstance(n, HlsNetNodeExplicitSync) and not n._isMarkedRemoved:
                    netlistReduceExplicitSyncFlags(dbgTracer, n, None)
            changed |= parent.filterNodesUsingRemovedSet()

        if changed:
            return PreservedAnalysisSet.preserveReachablity()
        else:
            return PreservedAnalysisSet.preserveAll()
