from typing import Union, Optional, Generator

from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.ssa.value import SsaValue
from hwtLib.handshaked.builder import HsBuilder


class HlsNetNodeReadBackwardEdge(HlsNetNodeRead):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src:Union[RtlSignal, Interface]):
        HlsNetNodeRead.__init__(self, netlist, src)
        self.associated_write: Optional[HlsNetNodeWriteBackwardEdge] = None

    def allocateRtlInstance(self, allocator:"AllocatorArchitecturalElement") -> TimeIndependentRtlResource:
        op_out = self._outputs[0]
        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass

        if self.associated_write.allocateAsBuffer:
            # allocate as a read from buffer output interface
            return HlsNetNodeRead.allocateRtlInstance(self, allocator)
        else:
            # allocate as a register
            name = self.name

            init = self.associated_write.channel_init_values
            if init:
                if len(init) > 1:
                    raise NotImplementedError(self, init)
            else:
                init = (0,)
            reg = allocator._reg(name if name else f"{allocator.namePrefix:s}program_starter", self.getRtlDataSig()._dtype, def_val=init[0])

            # create RTL signal expression base on operator type
            regTir = TimeIndependentRtlResource(reg, self.scheduledOut[0], allocator)
            allocator.netNodeToRtl[op_out] = regTir

            return regTir


class HlsNetNodeWriteBackwardEdge(HlsNetNodeWrite):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    
    :ivar allocateAsBuffer: A flag which specifies how this object should be allocated.
        If True this object allocates a buffer of length specified by time difference between read/write or register if the value is False.
    :ivar channel_init_values: Optional tuple for value initialization.
    """

    def __init__(self, netlist:"HlsNetlistCtx",
                 src,
                 dst:Union[RtlSignal, Interface, SsaValue],
                 channel_init_values=()):
        HlsNetNodeWrite.__init__(self, netlist, src, dst)
        self.associated_read: Optional[HlsNetNodeReadBackwardEdge] = None
        self.channel_init_values = channel_init_values
        self.allocateAsBuffer = True
        self.buff_name = None

    def associate_read(self, read: HlsNetNodeReadBackwardEdge):
        assert isinstance(read, HlsNetNodeReadBackwardEdge), read
        self.associated_read = read
        read.associated_write = self

    def allocateRtlInstance(self, allocator:"AllocatorArchitecturalElement") -> TimeIndependentRtlResource:
        try:
            return allocator.netNodeToRtl[self]
        except KeyError:
            pass

        if self.allocateAsBuffer:
            res = HlsNetNodeWrite.allocateRtlInstance(self, allocator)
            allocator._afterNodeInstantiated(self, res)

            src_write = self
            dst_read: HlsNetNodeReadBackwardEdge = self.associated_read
            assert dst_read is not None
            dst_t = dst_read.scheduledOut[0]
            src_t = src_write.scheduledIn[0]
            assert dst_t <= src_t, ("This was supposed to be backward edge", dst_t, src_t, src_write, dst_read)
            # 1 register at minimum, because we need to break a combinational path
            # the size of buffer is derived from the latency of operations between the io ports
            reg_cnt = max((src_t - dst_t) / allocator.netlist.normalizedClkPeriod, 1)

            # :note: latency is 1-2 to break ready chain (it is not always required, but the check is not implemented)
            buffs = HsBuilder(allocator.netlist.parentUnit, src_write.dst,
                              self.buff_name if self.buff_name else "hls_backward_buff")\
                .buff(reg_cnt, latency=(1, 2), init_data=self.channel_init_values)\
                .end
            dst_read.src(buffs)
        else:
            assert self.associated_read in allocator.allNodes, (self, allocator)
            reg: TimeIndependentRtlResource = allocator.netNodeToRtl[self.associated_read._outputs[0]]
            src = allocator.instantiateHlsNetNodeOut(self.dependsOn[0])
            res = reg.valuesInTime[0].data(src.get(self.scheduledOut[0]).data)

        allocator.netNodeToRtl[self] = res

        return res

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        yield self.associated_read
