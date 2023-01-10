from hwtHls.architecture.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.netlist.context import HlsNetlistCtx


class RtlNetlistPassAddSyncSigNames(RtlNetlistPass):
    """
    :see: :class:`hwtHls.architecture.allocator.HlsAllocator`
    """

    def apply(self, hls:"HlsScope", netlist:HlsNetlistCtx):
        netlist.allocator._dbgAddNamesToSyncSignals = True
        for elm in netlist.allocator._archElements:
            elm._dbgAddNamesToSyncSignals = True
            assert not elm._syncAllocated, elm
