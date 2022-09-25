from collections import deque
from typing import Set, List, Deque

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassDisaggregateAggregates(HlsNetlistPass):
    """
    Replace aggregated clusters with original nodes.
    """

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        removedNodes: Set[HlsNetNodeAggregate] = set()
        addedNodes: List[HlsNetNode] = []
        # discover clusters of bitwise operators
        toExpand: Deque[HlsNetNodeAggregate] = deque(n for n in netlist.nodes if isinstance(n, HlsNetNodeAggregate))
        while toExpand:
            n: HlsNetNodeAggregate = toExpand.pop()
            for subNode in n.disaggregate():
                if isinstance(subNode, HlsNetNodeRead):
                    netlist.inputs.append(subNode)
                elif isinstance(subNode, HlsNetNodeWrite):
                    netlist.outputs.append(subNode)
                elif isinstance(subNode, HlsNetNodeAggregate):
                    toExpand.append(subNode)
                else:
                    assert subNode is not None
                    addedNodes.append(subNode)

            n.destroy()
            removedNodes.add(n)

        addedNodes.extend([n for n in netlist.nodes if n not in removedNodes])
        netlist.nodes = addedNodes
        # drop builder.operatorCache because we removed most of bitwise operator from the circuit
        netlist.builder.operatorCache.clear()
