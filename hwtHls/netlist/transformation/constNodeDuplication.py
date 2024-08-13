from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, link_hls_nodes
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassConstNodeDuplication(HlsNetlistPass):
    """
    Duplicate HlsNetNodeConst so every instance has just a single use.
    :note: Used before scheduling to reduce fanout of the const nodes to speedup the sheduler alg. 
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        builder = netlist.builder
        changed = False
        for n in netlist.nodes:
            if isinstance(n, HlsNetNodeConst) and len(n.usedBy[0]) > 1:
                o = n._outputs[0]
                uses = n.usedBy[0]
                changed = True
                for _ in range(len(uses) - 1):
                    use = uses[-1]
                    unlink_hls_nodes(o, use)
                    newO = builder.buildConst(n.val)
                    link_hls_nodes(newO, use)

        if changed:
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
