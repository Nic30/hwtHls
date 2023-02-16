import html
from itertools import chain
import pydot
from typing import List, Dict

from hwtHls.netlist.analysis.syncReach import HlsNetlistAnalysisPassSyncReach
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.translation.toGraphwiz import HwtHlsNetlistToGraphwiz
from hwtHls.platform.fileUtils import OutputStreamGetter


class HwtHlsNetlistSyncReachToGraphwiz(HwtHlsNetlistToGraphwiz):
    """
    Generate a Graphwiz (dot) diagram of sync domains extracted from the netlist.
    """

    def __init__(self, name:str, nodes:List[HlsNetNode]):
        HwtHlsNetlistToGraphwiz.__init__(self, name, nodes)
        self.syncReachGroupOfSyncNode: Dict[HlsNetNode, pydot.Cluster] = {}
    
    def _getGraph(self, n:HlsNetNode):
        try:
            return self.syncReachGroupOfSyncNode[n]
        except KeyError:
            return self.graph

    def construct(self, syncReach: HlsNetlistAnalysisPassSyncReach):
        g = self.graph
        syncReachGroupOfSyncNode = self.syncReachGroupOfSyncNode
        clusterNodes = []
        for island in syncReach.syncIslands:
            clusterNode = pydot.Cluster(f"n{self._getNewNodeId()}", label=f'"{html.escape(repr(island)):s}"')
            clusterNodes.append(clusterNode)
            g.add_subgraph(clusterNode)
            for n in chain(island.inputs, island.nodes):  # 
                assert n not in syncReachGroupOfSyncNode, (
                    n, clusterNode.get("label"), syncReachGroupOfSyncNode[n].get("label"))
                syncReachGroupOfSyncNode[n] = clusterNode

        for clusterNode, island in zip(clusterNodes, syncReach.syncIslands):
            for n in chain(island.controlOutputs, island.dataOutputs):
                n: HlsNetNode
                if n not in syncReachGroupOfSyncNode:
                    syncReachGroupOfSyncNode[n] = clusterNode
            
        super(HwtHlsNetlistSyncReachToGraphwiz, self).construct()
    
    def dumps(self):
        return self.graph.to_string()


class HlsNetlistPassSyncReachToGraphwiz(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        name = netlist.label
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphwiz = HwtHlsNetlistSyncReachToGraphwiz(name, netlist.iterAllNodes())
            syncReach = netlist.getAnalysis(HlsNetlistAnalysisPassSyncReach)
            toGraphwiz.construct(syncReach)
            out.write(toGraphwiz.dumps())
        finally:
            if doClose:
                out.close()

