from itertools import islice
from typing import Set, List

from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.syncDomains import HlsNetlistAnalysisPassSyncDomains
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut, HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatedIoSyncScc import HlsNetNodeIoSyncScc
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassAggregateIoSyncSccs(HlsNetlistPass):
    """
    Extract cluster of nodes for each IO Strongly Connected Component (SCC) as a single node to simplify scheduling.
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        removedNodes: Set[HlsNetNode] = set()
        syncDomains:HlsNetlistAnalysisPassSyncDomains = netlist.getAnalysis(HlsNetlistAnalysisPassSyncDomains)
        updatedAggregateNodes: List[HlsNetNodeAggregate] = []
        # discover clusters of bitwise operators
        for scc in syncDomains.ioSccs:
            c: HlsNetlistClusterSearch = HlsNetlistClusterSearch.discoverFromNodeList(scc)
            assert c.nodes, "Each cluster needs to have some nodes"
            #hierarchyPath = hierarchy.nodePath[c.nodes[0]]
            #nodesOnSameHierarchyLevel = hierarchy.nodeHieararchy[hierarchyPath]
            parent = c.nodes[0].parent
            for otherNode in islice(c.nodes, 1, None):
                # :note: hierarchy should be build in a way that this assert is satisfied
                assert otherNode.parent is parent, (
                    "All cluster nodes must be on same hierarchy level", parent, otherNode.parent, c.nodes[0], otherNode)
            for n in c.nodes:
                assert not isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)), n

            # add newly created aggregate node to parent node container
            clusterNode = HlsNetNodeIoSyncScc(netlist, c.nodes)
            if parent is None:
                netlist.addNode(clusterNode)
            else:
                updatedAggregateNodes.append(parent)
                parent.addNode(clusterNode)
            c.substituteWithNode(clusterNode)
            removedNodes.update(c.nodes)

        changed = bool(syncDomains.ioSccs)
        if changed:
            # filter node containers
            for n in updatedAggregateNodes:
                n.filterNodesUsingSet(removedNodes, clearRemoved=False)
            netlist.filterNodesUsingSet(removedNodes)
            # drop builder.operatorCache because we removed most of bitwise operator from the circuit
            netlist.builder.operatorCache.clear()
            return PreservedAnalysisSet()
        else:
            return PreservedAnalysisSet.preserveAll()

