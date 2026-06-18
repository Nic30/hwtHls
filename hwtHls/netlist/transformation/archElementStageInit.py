from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassArchElementStageInit(HlsNetlistPass):
    """
    Init stage containers in ArchElements with from its nodes
    """

    def _ArchElementStageInit(self, elm: ArchElement):
        for n in elm.subNodes:
            assert n.scheduledZero is not None, ("Node must be scheduled", n, elm)
            assert n.scheduledZero >= 0, (n, elm, n.scheduledZero, n.scheduledIn, n.scheduledOut)
            elm._addNodeIntoScheduled(n.getFirstSchedZeroClkI(), n, allowNewClockWindow=True)
 
    @override
    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx):
        for elm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_POSTORDER):
            assert isinstance(elm, ArchElement), elm
            self._ArchElementStageInit(elm)

        return PreservedAnalysisSet.preserveAll()
