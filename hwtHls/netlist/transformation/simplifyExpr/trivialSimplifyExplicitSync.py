from typing import Set

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync


class HlsNetlistPassTrivialSimplifyExplicitSync(HlsNetlistPass):

    def __init__(self, dbgTracer: DebugTracer):
        self.dbgTracer = dbgTracer

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        dbgTracer = self.dbgTracer
        removed: Set[HlsNetNode] = netlist.builder._removedNodes
        for n in netlist.iterAllNodes():
            if isinstance(n, HlsNetNodeExplicitSync) and n not in removed:
                netlistReduceExplicitSyncFlags(dbgTracer, n, None, removed)
        if removed:
            netlist.filterNodesUsingSet(removed)
