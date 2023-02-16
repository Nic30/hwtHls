import html
from itertools import chain
import pydot
from typing import List, Dict

from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.translation.toGraphwiz import HwtHlsNetlistToGraphwiz
from hwtHls.platform.fileUtils import OutputStreamGetter


class HwtHlsNetlistBetweenSyncIslandsToGraphwiz(HwtHlsNetlistToGraphwiz):
    """
    Generate a Graphwiz (dot) diagram of sync domains extracted from the netlist.
    """

    def __init__(self, name:str, nodes:List[HlsNetNode]):
        HwtHlsNetlistToGraphwiz.__init__(self, name, nodes)
        self.syncIslandsGroupOfSyncNode: Dict[HlsNetNode, pydot.Cluster] = {}
    
    def _getGraph(self, n:HlsNetNode):
        try:
            return self.syncIslandsGroupOfSyncNode[n]
        except KeyError:
            return self.graph

    def construct(self, syncIslands: HlsNetlistAnalysisPassBetweenSyncIslands):
        g = self.graph
        syncIslandsGroupOfSyncNode = self.syncIslandsGroupOfSyncNode
        clusterNodes = []
        for island in syncIslands.syncIslands:
            clusterNode = pydot.Cluster(f"n{self._getNewNodeId()}", label=f'"{html.escape(repr(island)):s}"')
            clusterNodes.append(clusterNode)
            g.add_subgraph(clusterNode)
            for n in chain(island.inputs, island.nodes):  # 
                assert n not in syncIslandsGroupOfSyncNode, (
                    n, clusterNode.get("label"), syncIslandsGroupOfSyncNode[n].get("label"))
                syncIslandsGroupOfSyncNode[n] = clusterNode

        for clusterNode, island in zip(clusterNodes, syncIslands.syncIslands):
            for n in island.outputs:
                n: HlsNetNode
                if n not in syncIslandsGroupOfSyncNode:
                    syncIslandsGroupOfSyncNode[n] = clusterNode
            
        super(HwtHlsNetlistBetweenSyncIslandsToGraphwiz, self).construct()
    
    def dumps(self):
        return self.graph.to_string()


class HlsNetlistPassBetweenSyncIslandsToGraphwiz(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        name = netlist.label
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphwiz = HwtHlsNetlistBetweenSyncIslandsToGraphwiz(name, netlist.iterAllNodes())
            syncIslands = netlist.getAnalysis(HlsNetlistAnalysisPassBetweenSyncIslands)
            toGraphwiz.construct(syncIslands)
            out.write(toGraphwiz.dumps())
        finally:
            if doClose:
                out.close()

