from typing import Set

from hwtHls.netlist.analysis.detectLoops import HlsNetlistAnalysisPassDetectLoops
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregatedLoop import HlsNetNodeLoop
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassAggregateLoops(HlsNetlistPass):
    """
    Extract cluster of nodes in a single loop.
    If loop contains sub loops they are also extracted to own HlsNetNodeLoop.

    :note: Loop nodes are aggregated to minimize loop body latency during scheduling.
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
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
