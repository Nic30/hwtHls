from typing import Optional, Dict

from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwt.hdl.operatorDefs import HwtOps


class HlsAndRtlNetlistPassAddSignalNamesToSync(HlsAndRtlNetlistPass):
    """
    :see: :class:`hwtHls.netlist.context.HlsNetlistCtx`
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        netlist._dbgAddSignalNamesToSync = True
        for elm in netlist.subNodes:
            assert isinstance(elm, ArchElement), elm
            elm._dbgAddSignalNamesToSync = True
            assert not elm._rtlSyncAllocated, elm

        return PreservedAnalysisSet.preserveAll()


class HlsAndRtlNetlistPassAddSignalNamesToData(HlsAndRtlNetlistPass):
    """
    :see: :class:`hwtHls.netlist.context.HlsNetlistCtx`
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        netlist._dbgAddSignalNamesToData = True
        for elm in netlist.subNodes:
            assert isinstance(elm, ArchElement), elm
            elm._dbgAddSignalNamesToData = True
            assert not elm._rtlSyncAllocated, elm

        return PreservedAnalysisSet.preserveAll()


class HlsAndRtlNetlistPassAddSignalForDeepExpr(HlsAndRtlNetlistPass):
    """
    This pass adds names to expression signals in RTL to improve readability and reduce generated code size.
    :note: RtlSignals without name are likely to be inlined into expressions in HDL.
    
    :ivar maxExprDepth: maximum depth of expression until it gets name assigned (and is tmp variable in HDL)
    :note: maxExprDepth == 1 will transform a + b + c to tmp = a + b; tmp2 = tmp + c
    :note: HwtOps.NOT is ignored in depth levels
    :ivar maxFanout: maximum number of output uses until it gets name assigned
    :ivar _depth: number of nodes this node and primary inputs, (0 means that node is primary inputs and has name)
    """

    def __init__(self, maxExprDepth:Optional[int]=3, maxFanout:Optional[int]=1):
        assert maxExprDepth is None or maxExprDepth > 0, maxExprDepth
        assert maxFanout is None or maxFanout > 0, maxFanout
        assert maxExprDepth is not None or maxFanout is not None
        HlsAndRtlNetlistPass.__init__(self)
        self.maxExprDepth = maxExprDepth
        self.maxFanout = maxFanout
        self._depth: Dict[HlsNetNodeOperator, int] = {}

    def _getNodeDepth(self, n: HlsNetNodeOperator):
        knownDepth = self._depth.get(n)
        if knownDepth is not None:
            return knownDepth
        elif n._rtlAddName or len(n._outputs) != 1:
            return 0
        elif n.operator != HwtOps.NOT and self.maxFanout is not None and len(n.usedBy[0]) > self.maxFanout:
            n._rtlAddName = True
            depth = 0
        else:
            depth = max((self._getNodeDepth(dep.obj) if isinstance(dep.obj, HlsNetNodeOperator) else 0
                          for dep in n.dependsOn))
            if n.operator != HwtOps.NOT:
                depth += 1
                if self.maxExprDepth is not None and depth >= self.maxExprDepth:
                    n._rtlAddName = True
                    depth = 0

        self._depth[n] = depth
        return depth

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if n._isMarkedRemoved:
                continue
            if isinstance(n, HlsNetNodeOperator):
                assert not n._isRtlAllocated, n
                if n._rtlAddName or n in self._depth:
                    # skipping already resolve
                    continue
                # resolve recursively
                self._getNodeDepth(n)

        return PreservedAnalysisSet.preserveAll()

