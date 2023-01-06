from typing import Set, Dict, List, Optional

from hwt.hdl.operatorDefs import BITWISE_OPS
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatedBitwiseOps import HlsNetNodeBitwiseOps
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.observableList import ObservableList


class HlsNetlistPassAggregateBitwiseOps(HlsNetlistPass):
    """
    Extract cluster of bitwise operators as a single node to simplify scheduling.
    
    :attention: If the netlist contains unused nodes it may cause problems during scheduling.
    """

    @staticmethod
    def _isBitwiseOperator(n: HlsNetNode):
        return isinstance(n, HlsNetNodeOperator) and n.operator in BITWISE_OPS
    
    def _registerInternalyStoredClusterInputs(self, n: HlsNetNodeAggregate, otherAggregateInputs: Dict[HlsNetNodeOut, UniqList[HlsNetNodeAggregate]]): 
        for dep in n.dependsOn:
            userList = otherAggregateInputs.get(dep, None)
            if userList is None:
                userList = otherAggregateInputs[dep] = UniqList()
            userList.append(n)

    def _searchClusters(self, nodes: ObservableList[HlsNetNode],
                        parentAggregate: Optional[HlsNetNodeAggregate],
                        seen: Set[HlsNetNode],
                        removedNodes: Set[HlsNetNode],
                        newOutMap: Dict[HlsNetNodeOut, HlsNetNodeOut],
                        otherAggregateInputs: Dict[HlsNetNodeOut, UniqList[HlsNetNodeAggregate]]) -> ObservableList[HlsNetNode]:
        for n in nodes:
            if n not in seen and self._isBitwiseOperator(n):
                cluster = HlsNetlistClusterSearch()
                cluster.discover(n, seen, self._isBitwiseOperator)
                if len(cluster.nodes) > 1:
                    for c in cluster.splitToPreventOuterCycles():
                        c: HlsNetlistClusterSearch
                        if len(c.nodes) > 1:
                            c.updateOuterInputs(newOutMap)
                            clusterNode = HlsNetNodeBitwiseOps(n.netlist, c.nodes)
                            nodes.append(clusterNode)
                            clusterOutputs = c.outputs
                            c.substituteWithNode(clusterNode)
                            assert clusterNode._inputs
                            assert clusterNode._inputsInside
                            assert clusterNode._outputs
                            assert clusterNode._outputsInside
                            
                            removedNodes.update(c.nodes)

                            for internO, o  in zip(clusterOutputs, clusterNode._outputs):
                                newOutMap[internO] = o
       
                            self._registerInternalyStoredClusterInputs(clusterNode, otherAggregateInputs) 

            elif isinstance(n, HlsNetNodeAggregate) and not isinstance(n, HlsNetNodeBitwiseOps):
                # the input uses were updated if something was extracted
                n._subNodes = self._searchClusters(n._subNodes, n, seen, removedNodes, newOutMap, otherAggregateInputs)

        return ObservableList(n for n in nodes if n not in removedNodes)

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        seen: Set[HlsNetNodeOperator] = set()
        removedNodes: Set[HlsNetNode] = set()
        newOutMap: Dict[HlsNetNodeOut, HlsNetNodeOut] = {}
        otherAggregateInputs: Dict[HlsNetNodeOut, UniqList[HlsNetNodeAggregate]] = {}
        for n in netlist.nodes:
            if isinstance(n, HlsNetNodeAggregate):
                self._registerInternalyStoredClusterInputs(n, otherAggregateInputs)

        # discover clusters of bitwise operators
        netlist.nodes = self._searchClusters(netlist.nodes, None, seen, removedNodes, newOutMap, otherAggregateInputs)
        # drop builder.operatorCache because we removed most of bitwise operator from the circuit
        netlist.builder.operatorCache.clear()
