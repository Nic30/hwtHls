from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassArchElementStageInit(HlsNetlistPass):

    def _ArchElementStageInit(self, elm: ArchElement):
        clkPeriod = elm.netlist.normalizedClkPeriod
        for n in elm.subNodes:
            assert n.scheduledZero is not None, ("Node must be scheduled", n, elm)
            elm._addNodeIntoScheduled(n.scheduledZero // clkPeriod, n, allowNewClockWindow=True)
 
    @override
    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx):
        for elm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_POSTORDER):
            assert isinstance(elm, ArchElement), elm
            self._ArchElementStageInit(elm)

        return PreservedAnalysisSet.preserveAll()
