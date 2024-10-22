from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeIn
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassConstNodeDuplication(HlsNetlistPass):
    """
    Duplicate HlsNetNodeConst so every instance has just a single use.
    :note: Used before scheduling to reduce fanout of the const nodes to speedup the sheduler alg. 
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        changed = False
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if isinstance(n, HlsNetNodeConst) and len(n.usedBy[0]) > 1:
                n: HlsNetNodeConst
                o = n._outputs[0]
                uses = n.usedBy[0]
                changed = True
                builder = n.getHlsNetlistBuilder()
                for _ in range(len(uses) - 1):
                    use: HlsNetNodeIn = uses[-1]
                    use.disconnectFromHlsOut(o)
                    newO = builder.buildConst(n.val)
                    newO.connectHlsIn(use)

        if changed:
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
