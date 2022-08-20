from typing import Set, Dict, List

from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregatedBitwiseOps import HlsNetNodeBitwiseOps
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassDisaggregateBitwiseOps(HlsNetlistPass):
    """
    Replace cluster of bitwise operators with original nodes.
    """

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        seen: Set[HlsNetNodeOperator] = set()
        removedNodes: Set[HlsNetNodeBitwiseOps] = set()
        addedNodes: List[HlsNetNode] = []
        substitutionDict: Dict[HlsNetNodeOut, HlsNetNodeOut] = {}
        # discover clusters of bitwise operators
        for n in netlist.nodes:
            if n not in seen and isinstance(n, HlsNetNodeBitwiseOps):
                n: HlsNetNodeBitwiseOps
                cluster: HlsNetlistClusterSearch = n._subNodes
                addedNodes.extend(cluster.nodes)
                cluster.substituteSelfWithInternalNodes(n, substitutionDict)
                n.destroy()
                removedNodes.add(n)

        addedNodes.extend([n for n in netlist.nodes if n not in removedNodes])
        netlist.nodes = addedNodes
        
        # drop builder.operatorCache because we removed most of bitwise operator from the circuit
        netlist.builder.operatorCache.clear()
