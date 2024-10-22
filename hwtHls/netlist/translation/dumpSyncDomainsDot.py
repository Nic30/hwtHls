import html
import pydot
from typing import List, Dict

from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.syncDomains import HlsNetlistAnalysisPassSyncDomains
from hwtHls.netlist.analysis.syncGroupClusterContext import SyncGroupLabel
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.translation.dumpNodesDot import HwtHlsNetlistToGraphviz
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass


class HwtHlsNetlistSyncDomainsToGraphviz(HwtHlsNetlistToGraphviz):
    """
    Generate a Graphviz (dot) diagram of sync domains extracted from the netlist.
    """

    def __init__(self, name:str, nodes:List[HlsNetNode], expandAggregates:bool=False, addLegend:bool=True, addOrderingNodes:bool=True):
        HwtHlsNetlistToGraphviz.__init__(self, name, nodes, expandAggregates=expandAggregates, addLegend=addLegend, addOrderingNodes=addOrderingNodes)
        self.syncGroupOfSyncNode: Dict[HlsNetNodeExplicitSync, SyncGroupLabel] = {}
        self.groupGraphNodes: Dict[SyncGroupLabel, pydot.Cluster] = {}

    @override
    def _getGraph(self, n:HlsNetNode):
        try:
            syncGroup = self.syncGroupOfSyncNode[n]
        except KeyError:
            return self.graph, None, None
        return self.groupGraphNodes[syncGroup], None, None

    @override
    def construct(self, syncDomains: HlsNetlistAnalysisPassSyncDomains):
        g = self.graph

        groupGraphNodes = self.groupGraphNodes
        groupsSorted = syncDomains.syncDomains
        syncGroupOfSyncNode = self.syncGroupOfSyncNode
        for syncGroup, nodes in groupsSorted:
            groupLabel = ','.join(str(n._id) for n in syncGroup)

            clusterNode = pydot.Cluster(f"n{self._getNewNodeId()}", label=f'"SyncGroup({html.escape(groupLabel)})"')
            g.add_subgraph(clusterNode)
            groupGraphNodes[syncGroup] = clusterNode

            for n in nodes:
                assert n not in syncGroupOfSyncNode
                syncGroupOfSyncNode[n] = syncGroup

        super(HwtHlsNetlistSyncDomainsToGraphviz, self).construct()

    def dumps(self):
        return self.graph.to_string()


class HlsNetlistAnalysisPassDumpSyncDomainsDot(HlsNetlistAnalysisPass):

    def __init__(self, outStreamGetter: OutputStreamGetter, addLegend:bool=True):
        self.outStreamGetter = outStreamGetter
        self.addLegend = addLegend

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        name = netlist.label
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphviz = HwtHlsNetlistSyncDomainsToGraphviz(name, netlist.iterAllNodes(), addLegend=self.addLegend)
            syncDomains = netlist.getAnalysis(HlsNetlistAnalysisPassSyncDomains)
            toGraphviz.construct(syncDomains)
            out.write(toGraphviz.dumps())
        finally:
            if doClose:
                out.close()

