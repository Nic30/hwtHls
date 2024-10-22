from collections import deque
from typing import Deque

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregateTmpForScheduling
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.netlist.analysis.consistencyCheck import HlsNetlistPassConsistencyCheck


class HlsNetlistPassDisaggregateAggregates(HlsNetlistPass):
    """
    Replace aggregated clusters with original nodes.
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        changed = False
        modifiedElms: SetList[ArchElement, HlsNetlistCtx] = SetList()
        HlsNetlistPassConsistencyCheck()._checkAggregatePortsScheduling(netlist, False)
        for parent, nodes in netlist.iterNodesFlatWithParentByType(HlsNetNodeAggregateTmpForScheduling, postOrder=True):
            nodes = tuple(nodes)
            if nodes:
                if not isinstance(parent, HlsNetNodeAggregateTmpForScheduling):
                    modifiedElms.append(parent)
                _addedNodes: Deque[HlsNetNode] = deque()
                for n in nodes:
                    n: HlsNetNodeAggregateTmpForScheduling
                    if n._isMarkedRemoved:
                        continue

                    # :note: because of postOrder=True any children can not contain anything to expand
                    for subNode in n.disaggregate():
                        assert subNode is not None
                        _addedNodes.append(subNode)

                    changed = True

                addedNodes = []
                while _addedNodes:  # expanded nodes may contain nodes which may also require expansion
                    n = _addedNodes.popleft()
                    if isinstance(n, HlsNetNodeAggregateTmpForScheduling):
                        if n._isMarkedRemoved:
                            continue

                        # :note: because of postOrder=True any children can not contain anything to expand
                        for subNode in n.disaggregate():
                            assert subNode is not None
                            _addedNodes.append(subNode)

                        changed = True
                    else:
                        addedNodes.append(n)

                parent.addNodes(addedNodes)
                # drop builder.operatorCache because we removed most of bitwise operator from the circuit
                parent.builder.operatorCache.clear()
                HlsNetlistPassConsistencyCheck()._checkAggregatePortsScheduling(netlist, False)

        for elm in modifiedElms:
            changed |= elm.filterNodesUsingRemovedSet(recursive=False)

        if changed:
            return PreservedAnalysisSet.preserveSchedulingOnly()
        else:
            return PreservedAnalysisSet.preserveAll()
