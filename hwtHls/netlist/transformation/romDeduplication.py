from typing import Dict

from hwt.hdl.types.array import HArray
from hwt.hdl.types.arrayVal import HArrayVal
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassRomDeduplication(HlsNetlistPass):
    """
    Deduplicate HlsNetNodeConst nodes with large array value.

    :note: Used after scheduling to remove code duplication.
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        builder = netlist.builder
        constCache: Dict[HArrayVal, HlsNetNodeOut] = {}
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
        netlist.filterNodesUsingSet(removed)
