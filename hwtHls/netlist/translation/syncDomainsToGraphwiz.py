import html
import pydot
from typing import List, Dict

from hwtHls.netlist.analysis.syncDomains import HlsNetlistAnalysisPassSyncDomains
from hwtHls.netlist.analysis.syncGroupClusterContext import SyncGroupLabel
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.translation.toGraphwiz import HwtHlsNetlistToGraphwiz
from hwtHls.platform.fileUtils import OutputStreamGetter


class HwtHlsNetlistSyncDomainsToGraphwiz(HwtHlsNetlistToGraphwiz):
    """
    Generate a Graphwiz (dot) diagram of sync domains extracted from the netlist.
    """

    def __init__(self, name:str, nodes:List[HlsNetNode]):
        HwtHlsNetlistToGraphwiz.__init__(self, name, nodes)
        self.syncGroupOfSyncNode: Dict[HlsNetNodeExplicitSync, SyncGroupLabel] = {}
        self.groupGraphNodes: Dict[SyncGroupLabel, pydot.Cluster] = {}
    
    def _getGraph(self, n:HlsNetNode):
        try:
            syncGroup = self.syncGroupOfSyncNode[n]
        except KeyError:
            return self.graph
        return self.groupGraphNodes[syncGroup]
        
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

        super(HwtHlsNetlistSyncDomainsToGraphwiz, self).construct()
    
    def dumps(self):
        return self.graph.to_string()


class HlsNetlistPassSyncDomainsToGraphwiz(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        name = netlist.label
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphwiz = HwtHlsNetlistSyncDomainsToGraphwiz(name, netlist.iterAllNodes())
            syncDomains = netlist.getAnalysis(HlsNetlistAnalysisPassSyncDomains)
            toGraphwiz.construct(syncDomains)
            out.write(toGraphwiz.dumps())
        finally:
            if doClose:
                out.close()

