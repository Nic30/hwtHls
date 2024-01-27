from itertools import islice
from typing import Set, List

from hwtHls.netlist.analysis.nodeParentAggregate import HlsNetlistAnalysisPassNodeParentAggregate
from hwtHls.netlist.analysis.syncDomains import HlsNetlistAnalysisPassSyncDomains
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut, HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatedIoSyncScc import HlsNetNodeIoSyncScc
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassAggregateIoSyncSccs(HlsNetlistPass):
    """
    Extract cluster of nodes for each IO Strongly Connected Component (SCC) as a single node to simplify scheduling.
    """

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        removedNodes: Set[HlsNetNode] = set()
        syncDomains:HlsNetlistAnalysisPassSyncDomains = netlist.getAnalysis(HlsNetlistAnalysisPassSyncDomains)
        hierarchy: HlsNetlistAnalysisPassNodeParentAggregate = netlist.getAnalysis(HlsNetlistAnalysisPassNodeParentAggregate)
        updatedAggregateNodes: List[HlsNetNodeAggregate] = []
        try:
            # discover clusters of bitwise operators
            for scc in syncDomains.ioSccs:
                c: HlsNetlistClusterSearch = HlsNetlistClusterSearch.discoverFromNodeList(scc)
                assert c.nodes, "Each cluster needs to have some nodes"
                hierarchyPath = hierarchy.nodePath[c.nodes[0]]
                nodesOnSameHierarchyLevel = hierarchy.nodeHieararchy[hierarchyPath]
                for otherNode in islice(c.nodes, 1, None):
                    # :note: hierarchy should be build in a way that this assert is satisfied
                    assert otherNode in nodesOnSameHierarchyLevel, (
                        "All cluster nodes must be on same hierarchy level", hierarchyPath, c.nodes[0], otherNode)
                for n in c.nodes:
                    assert not isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)), n

                # add newly created aggregate node to parent node container
                clusterNode = HlsNetNodeIoSyncScc(netlist, c.nodes)
                if len(hierarchyPath) == 0:
                    netlist.nodes.append(clusterNode)
                else:
                    parent = hierarchyPath[-1]
                    updatedAggregateNodes.append(parent)
                    parent._subNodes.append(clusterNode)
                c.substituteWithNode(clusterNode)
                removedNodes.update(c.nodes)

            # filter node containers
            for n in updatedAggregateNodes:
                n.filterNodesUsingSet(removedNodes)
            netlist.filterNodesUsingSet(removedNodes)
            # drop builder.operatorCache because we removed most of bitwise operator from the circuit
            netlist.builder.operatorCache.clear()
        finally:
            netlist.invalidateAnalysis(HlsNetlistAnalysisPassNodeParentAggregate)
