from typing import Set, Dict, List, Optional, Union

from hwt.hdl.operatorDefs import BITWISE_OPS
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatedBitwiseOps import HlsNetNodeBitwiseOps
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.observableList import ObservableList
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassAggregateBitwiseOps(HlsNetlistPass):
    """
    Extract cluster of bitwise operators as a single node to simplify scheduling.
    
    :attention: If the netlist contains unused nodes it may cause problems during scheduling.
    """

    @staticmethod
    def _isBitwiseOperator(n: HlsNetNode):
        return isinstance(n, HlsNetNodeOperator) and n.operator in BITWISE_OPS

    def _registerInternalyStoredClusterInputs(self, n: HlsNetNodeAggregate, otherAggregateInputs: Dict[HlsNetNodeOut, SetList[HlsNetNodeAggregate]]):
        for dep in n.dependsOn:
            userList = otherAggregateInputs.get(dep, None)
            if userList is None:
                userList = otherAggregateInputs[dep] = SetList()
            userList.append(n)

    def _searchClusters(self, parent: Union[HlsNetlistCtx, HlsNetNodeAggregate],
                        otherAggregateInputs: Dict[HlsNetNodeOut, SetList[HlsNetNodeAggregate]]) -> ObservableList[HlsNetNode]:
        seen: Set[HlsNetNodeOperator] = set()
        removedNodes: Set[HlsNetNode] = set()
        newOutMap: Dict[HlsNetNodeOut, HlsNetNodeOut] = {}
        changed = False
        changedOnThisLevel = False
        for n in parent.subNodes:
            if n not in seen and self._isBitwiseOperator(n):
                cluster = HlsNetlistClusterSearch()
                cluster.discover(n, seen, self._isBitwiseOperator)
                if len(cluster.nodes) > 1:
                    for c in cluster.splitToPreventOuterCycles():
                        c: HlsNetlistClusterSearch
                        if len(c.nodes) > 1:
                            changedOnThisLevel = True
                            c.updateOuterInputs(newOutMap)
                            clusterNode = HlsNetNodeBitwiseOps(n.netlist, c.nodes)
                            parent.addNode(clusterNode)
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
                changed |= self._searchClusters(n, otherAggregateInputs)

        if changedOnThisLevel:
            parent.filterNodesUsingSet(removedNodes, recursive=False)
            # drop builder.operatorCache because we removed most of bitwise operator from the circuit
            builder = parent.getHlsNetlistBuilder()
            builder.operatorCache.clear()

        return changed or changedOnThisLevel

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:

        otherAggregateInputs: Dict[HlsNetNodeOut, SetList[HlsNetNodeAggregate]] = {}
        for n in netlist.subNodes:
            if isinstance(n, HlsNetNodeAggregate):
                self._registerInternalyStoredClusterInputs(n, otherAggregateInputs)

        # discover clusters of bitwise operators
        changed = self._searchClusters(netlist, otherAggregateInputs)
        if changed:
            return PreservedAnalysisSet()
        else:
            return PreservedAnalysisSet.preserveAll()
