from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.netlist.nodes.archElement import ArchElement


class HlsNetlistPassMultiClockNodeSplit(HlsNetlistPass):
    """
    Split nodes crossing clock window boundary.
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        changed = False
        clkPeriod = netlist.normalizedClkPeriod
        for node in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            node: HlsNetNode
            if isinstance(node, HlsNetNodeAggregate):
                assert isinstance(node, ArchElement), ("All aggregates should be already dissolved", node)

            if node.isMulticlock:
                parent: ArchElement = node.parent
                assert parent is not None, ("Node is expected to be in ArchElement", node)
                for newNode in node.splitOnClkWindows():
                    parent._addNodeIntoScheduled(newNode.scheduledZero // clkPeriod, newNode)
                    changed = True

        if changed:
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()

