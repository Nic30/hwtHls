from typing import Set, Dict

from hwt.hdl.operatorDefs import BITWISE_OPS
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregatedBitwiseOps import HlsNetNodeBitwiseOps
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassAggregateBitwiseOps(HlsNetlistPass):
    """
    Extract cluster of bitwise operators as a single node to simplify scheduling.
    """

    def _isBitwiseOperator(self, n: HlsNetNode):
        return isinstance(n, HlsNetNodeOperator) and n.operator in BITWISE_OPS
        
    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        seen: Set[HlsNetNodeOperator] = set()
        removedNodes: Set[HlsNetNode] = set()
        newOutMap: Dict[HlsNetNodeOut, HlsNetNodeOut] = {}
        # discover clusters of bitwise operators
        for n in netlist.nodes:
            if n not in seen and self._isBitwiseOperator(n):
                    cluster = HlsNetlistClusterSearch()
                    cluster.discover(n, seen, self._isBitwiseOperator)
                    if len(cluster.nodes) > 1:
                        for c in cluster.splitToPreventOuterCycles():
                            if len(c.nodes) > 1:
                                c.updateOuterInputs(newOutMap)
                                clusterNode = HlsNetNodeBitwiseOps(netlist, c)
                                netlist.nodes.append(clusterNode)
                                c.substituteWithNode(clusterNode)
                                removedNodes.update(c.nodes)
                                for o, internO in zip(clusterNode._outputs, c.outputs):
                                    newOutMap[internO] = o
                                clusterNode._replaceAllOuterInputsPlaceholders(newOutMap)

        netlist.nodes = [n for n in netlist.nodes if n not in removedNodes]
