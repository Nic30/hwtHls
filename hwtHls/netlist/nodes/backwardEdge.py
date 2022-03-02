from typing import Union, Optional, Generator

from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.ssa.value import SsaValue
from hwtLib.handshaked.builder import HsBuilder
from hwtHls.allocator.fsmContainer import AllocatorFsmContainer


class HlsNetNodeReadBackwardEdge(HlsNetNodeRead):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    """

    def __init__(self, parentHls:"HlsPipeline",
        src:Union[RtlSignal, Interface]):
        HlsNetNodeRead.__init__(self, parentHls, src)
        self.associated_write: Optional[HlsNetNodeWriteBackwardEdge] = None


class HlsNetNodeWriteBackwardEdge(HlsNetNodeWrite):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    """

    def __init__(self, parentHls:"HlsPipeline",
                 src,
                 dst:Union[RtlSignal, Interface, SsaValue],
                 channel_init_values=()):
        HlsNetNodeWrite.__init__(self, parentHls, src, dst)
        self.associated_read: Optional[HlsNetNodeReadBackwardEdge] = None
        self.channel_init_values = channel_init_values

    def associate_read(self, read: HlsNetNodeReadBackwardEdge):
        assert isinstance(read, HlsNetNodeReadBackwardEdge), read
        self.associated_read = read
        read.associated_write = self

    def isLocalToFsm(self, allocator:"AllocatorArchitecturalElement"):
        return isinstance(allocator, AllocatorFsmContainer) and self.associated_read in allocator.allNodes
        
    def allocateRtlInstance(self, allocator:"AllocatorArchitecturalElement") -> TimeIndependentRtlResource:
        # [todo] check to prevent re instantiation
        # [todo] instantiate also ports there (currently they are instantiated when translating to HlsNetlist)
        # if self.isLocalToFsm(allocator):
        #    raise NotImplementedError("Do not instantiate buffer use just register")

        res = HlsNetNodeWrite.allocateRtlInstance(self, allocator)
        src_write = self
        dst_read: HlsNetNodeReadBackwardEdge = self.associated_read
        assert dst_read is not None
        dst_t = dst_read.scheduledOut[0]
        src_t = src_write.scheduledIn[0]
        assert dst_t <= src_t, ("This was supposed to be backward edge", src_write, dst_read)
        # 1 register at minimum, because we need to break a comibnational path
        # the size of buffer is derived from the latency of operations between the io ports
        reg_cnt = max((src_t - dst_t) / allocator.parentHls.clk_period, 1)

        # :note: latency is 1-2 to break ready chain (it is not always required, but the check is not implemented)
        buffs = HsBuilder(allocator.parentHls.parentUnit, src_write.dst,
                          "hls_backward_buff")\
            .buff(reg_cnt, latency=(1, 2), init_data=self.channel_init_values)\
            .end
        dst_read.src(buffs)
        return res

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        yield self.associated_read
