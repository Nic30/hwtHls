from typing import Set

from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.detectLoops import HlsNetlistAnalysisPassDetectLoops
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregatedLoop import HlsNetNodeLoop
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassAggregateLoops(HlsNetlistPass):
    """
    Extract cluster of nodes in a single loop.
    If loop contains sub loops they are also extracted to own HlsNetNodeLoop.

    :note: Loop nodes are aggregated to minimize loop body latency during scheduling.
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        removedNodes: Set[HlsNetNode] = set()
        loops:HlsNetlistAnalysisPassDetectLoops = netlist.getAnalysis(HlsNetlistAnalysisPassDetectLoops)
        for loop in loops.loops:
            c: HlsNetlistClusterSearch = HlsNetlistClusterSearch.discoverFromNodeList(loop.nodes)
            clusterNode = HlsNetNodeLoop(netlist, c.nodes)
            netlist.nodes.append(clusterNode)
            c.substituteWithNode(clusterNode)
            removedNodes.update(c.nodes)

        netlist.filterNodesUsingSet(removedNodes)
        # drop builder.operatorCache because we removed most of bitwise operator from the circuit
        netlist.builder.operatorCache.clear()

        changed = bool(loops.loops)
        if changed:
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
