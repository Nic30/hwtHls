from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsAndRtlNetlistPassAddSignalNamesToSync(HlsAndRtlNetlistPass):
    """
    :see: :class:`hwtHls.netlist.context.HlsNetlistCtx`
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        netlist._dbgAddSignalNamesToSync = True
        for elm in netlist.nodes:
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
        for elm in netlist.nodes:
            assert isinstance(elm, ArchElement), elm
            elm._dbgAddSignalNamesToData = True
            assert not elm._rtlSyncAllocated, elm

        return PreservedAnalysisSet.preserveAll()
