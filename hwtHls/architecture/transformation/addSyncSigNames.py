from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement


class HlsAndRtlNetlistPassAddSignalNamesToSync(HlsAndRtlNetlistPass):
    """
    :see: :class:`hwtHls.netlist.context.HlsNetlistCtx`
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        netlist._dbgAddSignalNamesToSync = True
        for elm in netlist.nodes:
            assert isinstance(elm, ArchElement), elm
            elm._dbgAddSignalNamesToSync = True
            assert not elm._rtlSyncAllocated, elm


class HlsAndRtlNetlistPassAddSignalNamesToData(HlsAndRtlNetlistPass):
    """
    :see: :class:`hwtHls.netlist.context.HlsNetlistCtx`
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        netlist._dbgAddSignalNamesToData = True
        for elm in netlist.nodes:
            assert isinstance(elm, ArchElement), elm
            elm._dbgAddSignalNamesToData = True
            assert not elm._rtlSyncAllocated, elm
