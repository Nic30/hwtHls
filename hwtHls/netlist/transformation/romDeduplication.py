from typing import Dict, Union

from hwt.hdl.types.array import HArray
from hwt.hdl.types.arrayConst import HArrayConst
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassRomDeduplication(HlsNetlistPass):
    """
    De-duplicate HlsNetNodeConst nodes with large array value.

    :note: Used after scheduling to remove code duplication.
    """

    def _runOnNodes(self, parent: Union[HlsNetlistCtx, HlsNetNodeAggregate]) -> bool:
        changed = False
        constCache: Dict[HArrayConst, HlsNetNodeOut] = {}
        for n in parent.subNodes:
            if isinstance(n, HlsNetNodeConst):
                n: HlsNetNodeConst
                v = n.val
                if isinstance(v._dtype, HArray):
                    o = n._outputs[0]
                    cur = constCache.get(v, None)
                    if cur is None:
                        constCache[v] = o
                    else:
                        n.getHlsNetlistBuilder().replaceOutput(o, cur, True)
                        assert not n._inputs, n
                        n.markAsRemoved()
                        changed = True

            elif isinstance(n, HlsNetNodeAggregate):
                changed |= self._runOnNodes(n)

        if parent.builder._removedNodes:
            parent.filterNodesUsingRemovedSet(recursive=False)
            changed = True

        return changed

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        changed = self._runOnNodes(netlist)
        if changed:
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
