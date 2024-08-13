from typing import Dict

from hwt.hdl.types.array import HArray
from hwt.hdl.types.arrayConst import HArrayConst
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassRomDeduplication(HlsNetlistPass):
    """
    De-duplicate HlsNetNodeConst nodes with large array value.

    :note: Used after scheduling to remove code duplication.
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        builder = netlist.builder
        constCache: Dict[HArrayConst, HlsNetNodeOut] = {}
        removed = set()
        for n in netlist.nodes:
            if isinstance(n, HlsNetNodeConst):
                n: HlsNetNodeConst
                v = n.val
                if isinstance(v._dtype, HArray):
                    o = n._outputs[0]
                    cur = constCache.get(v, None)
                    if cur is None:
                        constCache[v] = o
                    else:
                        builder.replaceOutput(o, cur, True)
                        assert not n._inputs, n
                        removed.add(n)
        if removed:
            netlist.filterNodesUsingSet(removed)
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
