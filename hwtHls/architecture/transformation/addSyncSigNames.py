from hwtHls.architecture.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement


class RtlNetlistPassAddSignalNamesToSync(RtlNetlistPass):
    """
    :see: :class:`hwtHls.netlist.context.HlsNetlistCtx`
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        netlist._dbgAddSignalNamesToSync = True
        for elm in netlist.nodes:
            assert isinstance(elm, ArchElement), elm
            elm._dbgAddSignalNamesToSync = True
            assert not elm._rtlSyncAllocated, elm


class RtlNetlistPassAddSignalNamesToData(RtlNetlistPass):
    """
    :see: :class:`hwtHls.netlist.context.HlsNetlistCtx`
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        netlist._dbgAddSignalNamesToData = True
        for elm in netlist.nodes:
            assert isinstance(elm, ArchElement), elm
            elm._dbgAddSignalNamesToData = True
            assert not elm._rtlSyncAllocated, elm
