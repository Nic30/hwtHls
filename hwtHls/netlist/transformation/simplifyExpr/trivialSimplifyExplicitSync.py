from hwt.constants import READ
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.memoryAllocationMetaNode import HlsNetNodeWriteMemoryAllocationCmd, \
    HlsNetNodeReadMemoryAllocationReadData
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import iterAllHierachies
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.netlist.nodes.memoryAllocationMeta import MemoryAllocationMeta
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain


def MemoryAllocationMeta_isRom(mem: MemoryAllocationMeta):
    for u in mem.users:
        if isinstance(u, HlsNetNodeWriteMemoryAllocationCmd):
            if u.cmd != READ:
                return False
        else:
            assert isinstance(u, HlsNetNodeReadMemoryAllocationReadData), u

    return True


class HlsNetlistPassTrivialSimplifyExplicitSync(HlsNetlistPass):

    def __init__(self, dbgTracer: DebugTracer):
        self.dbgTracer = dbgTracer

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        dbgTracer = self.dbgTracer
        changed = False
        localMemories: dict[MemoryAllocationMeta, bool] = {}
        for parent in iterAllHierachies(netlist):
            for n in parent.subNodes:
                if n._isMarkedRemoved:
                    continue
                if isinstance(n, HlsNetNodeExplicitSync):
                    if isinstance(n, HlsNetNodeWriteMemoryAllocationCmd) and n.cmd == READ:
                        mem: MemoryAllocationMeta = n.dst
                        isRom = localMemories.get(mem)
                        if isRom is None:
                            isRom = MemoryAllocationMeta_isRom(mem)
                            localMemories[mem] = isRom
                        if isRom:
                            # for local roms we do not need to preserve orderng and load order from local ROM does not matter 
                            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, None)

                    netlistReduceExplicitSyncFlags(dbgTracer, n, None)
            changed |= parent.filterNodesUsingRemovedSet()

        if changed:
            return PreservedAnalysisSet.preserveReachablity()
        else:
            return PreservedAnalysisSet.preserveAll()
