from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, link_hls_nodes


class HlsNetlistPassConstNodeDuplication(HlsNetlistPass):
    """
    Duplicate HlsNetNodeConst so every instance has just a single use.
    """

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        builder = netlist.builder
        for n in netlist.nodes:
            if isinstance(n, HlsNetNodeConst) and len(n.usedBy[0]) > 1:
                o = n._outputs[0]
                uses = n.usedBy[0]
                for _ in range(len(uses) - 1):
                    use = uses[-1]
                    unlink_hls_nodes(o, use)
                    newO = builder.buildConst(n.val)
                    link_hls_nodes(newO, use)
