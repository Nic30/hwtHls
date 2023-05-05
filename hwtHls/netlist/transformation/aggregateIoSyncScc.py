from typing import Set

from hwtHls.netlist.analysis.syncDomains import HlsNetlistAnalysisPassSyncDomains
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregatedIoSyncScc import HlsNetNodeIoSyncScc
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.observableList import ObservableList
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassAggregateIoSyncSccs(HlsNetlistPass):
    """
    Extract cluster of nodes for each IO Strongly Connected Component (SCC) as a single node to simplify scheduling.
    """

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        removedNodes: Set[HlsNetNode] = set()
        syncDomains:HlsNetlistAnalysisPassSyncDomains = netlist.getAnalysis(HlsNetlistAnalysisPassSyncDomains)
        # discover clusters of bitwise operators
        for scc in syncDomains.ioSccs:
            c: HlsNetlistClusterSearch = HlsNetlistClusterSearch.discoverFromNodeList(scc)
            clusterNode = HlsNetNodeIoSyncScc(netlist, c.nodes)
            netlist.nodes.append(clusterNode)
            c.substituteWithNode(clusterNode)
            removedNodes.update(c.nodes)

        netlist.nodes = ObservableList(n for n in netlist.nodes if n not in removedNodes)
        netlist.inputs = ObservableList(n for n in netlist.inputs if n not in removedNodes)
        netlist.outputs = ObservableList(n for n in netlist.outputs if n not in removedNodes)
        # drop builder.operatorCache because we removed most of bitwise operator from the circuit
        netlist.builder.operatorCache.clear()
