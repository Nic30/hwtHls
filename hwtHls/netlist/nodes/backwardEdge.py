from enum import Enum
from itertools import chain
from math import ceil
from typing import Union, Optional, Generator

from hwt.code import If
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.defs import BIT
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import InputTimeGetter, SchedulizationDict
from hwtHls.ssa.value import SsaValue
from hwtLib.handshaked.builder import HsBuilder


class HlsNetNodeReadBackwardEdge(HlsNetNodeRead):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src:Union[RtlSignal, Interface]):
        HlsNetNodeRead.__init__(self, netlist, src)
        self.associated_write: Optional[HlsNetNodeWriteBackwardEdge] = None

    def getRtlValidSig(self, allocator: "ArchElement") -> Union[RtlSignalBase, HValue]:
        if self.associated_write.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
            if isinstance(self, HlsNetNodeReadControlBackwardEdge):
                o = self._outputs[0]
                assert o._dtype == BIT, (self, o._dtype)
                return allocator.instantiateHlsNetNodeOutInTime(o, self.scheduledOut[1]).data
            else:
                return BIT.from_py(1)

        return HlsNetNodeRead.getRtlValidSig(self, allocator)

    def allocateRtlInstance(self, allocator:"ArchElement") -> TimeIndependentRtlResource:
        op_out = self._outputs[0]
        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass
        w: HlsNetNodeWriteBackwardEdge = self.associated_write
        if w.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
            # allocate as a read from buffer output interface
            return HlsNetNodeRead.allocateRtlInstance(self, allocator)
        else:
            # allocate as a register

            init = self.associated_write.channel_init_values
            if init:
                assert w.allocationType == BACKEDGE_ALLOCATION_TYPE.REG, w.allocationType
                if len(init) > 1:
                    raise NotImplementedError(self, init)
            else:
                init = ((0,),)

            name = self.name
            assert name is not None, self
            dtype = self.getRtlDataSig()._dtype
            if w.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
                reg = allocator._reg(f"{allocator.namePrefix:s}{name:s}", dtype, def_val=init[0][0])
                reg.hidden = False
            else:
                assert w.allocationType == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE, w.allocationType
                reg = allocator._sig(f"{allocator.namePrefix:s}{name:s}", dtype)

            # create RTL signal expression base on operator type
            regTir = TimeIndependentRtlResource(reg, self.scheduledOut[0], allocator, False)
            allocator.netNodeToRtl[op_out] = regTir

            return regTir


class HlsNetNodeReadControlBackwardEdge(HlsNetNodeReadBackwardEdge):
    """
    Same as :class:`~.HlsNetNodeReadBackwardEdge` but for control channels
    """


class BACKEDGE_ALLOCATION_TYPE(Enum):
    """
    :cvar IMMEDIATE: The signal will be used as is without any buffer. This also means that the value of data is not stable and must be immediately used.
        An extra care must be taken to prove that this kind of buffer does not create a combinational loop.
    :cvar REG: Allocate as a DFF register. Used if it is proven that the size of buffer will be max 1 to spare HW resources and to simplify synchronization logic.
    :cvar BUFFER: Object allocates a buffer of length specified by time difference between read/write.
    """
    IMMEDIATE, REG, BUFFER = range(3)
    

class HlsNetNodeWriteBackwardEdge(HlsNetNodeWrite):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    
    :ivar channel_init_values: Optional tuple for value initialization.
    """

    def __init__(self, netlist:"HlsNetlistCtx",
                 src,
                 dst:Union[RtlSignal, Interface, SsaValue],
                 channel_init_values=()):
        HlsNetNodeWrite.__init__(self, netlist, src, dst)
        self.associated_read: Optional[HlsNetNodeReadBackwardEdge] = None
        self.channel_init_values = channel_init_values
        self.allocationType = BACKEDGE_ALLOCATION_TYPE.BUFFER
        self.buff_name = None

    def associate_read(self, read: HlsNetNodeReadBackwardEdge):
        assert isinstance(read, HlsNetNodeReadBackwardEdge), read
        self.associated_read = read
        read.associated_write = self

    def _extractEnableForNonBufferReg(self, allocator:"ArchElement"):
        """
        If this read-write pair is not instantiated as a buffer it means it does not have associated IO interface.
        In this specific case we have to explicitly resolve synchronization.
        """
        from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo            
        ioDiscovery: HlsNetlistAnalysisPassDiscoverIo = self.netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverIo)
       
        extraConds, skipWhen = allocator._copyChannelSync(self,
                  ioDiscovery.extraReadSync.get(self, None),
                  None,
                  None)

        if extraConds is not None or skipWhen is not None:
            if extraConds is not None:
                en = extraConds.resolve()
            else:
                en = BIT.from_py(1)
            if skipWhen is not None:
                sw = skipWhen.resolve()
                en = en & ~sw

            if isinstance(en, BitsVal):
                # current block en=1
                assert int(en) == 1, en
                return None
            else:
                assert isinstance(en, RtlSignal), en
                return en

        return None

    def allocateRtlInstance(self, allocator:"ArchElement") -> TimeIndependentRtlResource:
        try:
            return allocator.netNodeToRtl[self]
        except KeyError:
            pass

        if self.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
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
            reg_cnt = max(ceil((src_t - dst_t) / allocator.netlist.normalizedClkPeriod), 1)

            # :note: latency is 1-2 to break ready chain (it is not always required, but the check is not implemented)
            buffs = HsBuilder(allocator.netlist.parentUnit, src_write.dst,
                              self.buff_name if self.buff_name else "hls_backward_buff")\
                .buff(reg_cnt, latency=(1, 2), init_data=self.channel_init_values)\
                .end
            dst_read.src(buffs)
            for i in chain(dst_read.src._interfaces, buffs._interfaces):
                i._sig.hidden = False
            
        else:
            assert self.associated_read in allocator.allNodes, (self, allocator)
            t0 = self.scheduledOut[0]
            reg: TimeIndependentRtlResource = allocator.instantiateHlsNetNodeOut(self.associated_read._outputs[0])

            src = allocator.instantiateHlsNetNodeOut(self.dependsOn[0])
            res = reg.valuesInTime[0].data(src.get(t0).data)
            en = self._extractEnableForNonBufferReg(allocator)
            
            if en is not None:
                if self.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
                    res = If(en, res)
                else:
                    assert res._dtype == BIT, (res, res._dtype)
                    res = res & en

        allocator.netNodeToRtl[self] = res

        return res

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        yield self.associated_read

    def scheduleAlapCompaction(self, asapSchedule:SchedulizationDict, inputTimeGetter:Optional[InputTimeGetter]):
        if self.scheduledIn is not None:
            return self.scheduledIn

        wrSched = HlsNetNodeWrite.scheduleAlapCompaction(self, asapSchedule, inputTimeGetter)
        rd = self.associated_read
        rd.scheduleAlapCompaction(asapSchedule, inputTimeGetter)
        rdSched = rd.scheduledOut
        # if there are not any uses (which is common case when there is no ordering extra specification)
        # we want to minimize the size of the buffer. Because of this we place this write just behind associated read
        if rdSched[0] > wrSched[0]:
            nodeZeroTime = rdSched[0] - rd.outputWireDelay[0] + self.netlist.scheduler.epsilon
            self.scheduledIn = tuple(
                nodeZeroTime - in_delay
                for in_delay in self.inputWireDelay
            )
            
            self.scheduledOut = tuple(
                nodeZeroTime + out_delay
                for out_delay in self.outputWireDelay
            )
        return self.scheduledIn


class HlsNetNodeWriteControlBackwardEdge(HlsNetNodeWriteBackwardEdge):
    """
    Same as :class:`~.HlsNetNodeWriteBackwardEdge` but for control channels
    """

    def allocateRtlInstance(self, allocator:"ArchElement") -> TimeIndependentRtlResource:
        try:
            return allocator.netNodeToRtl[self]
        except KeyError:
            pass
        res = super(HlsNetNodeWriteControlBackwardEdge, self).allocateRtlInstance(allocator)
        if self.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
            # if it is just register and both read and write are in same architectural element
            if isinstance(res, If):
                # in FSM we have to clear the control flag if it was not set in this write
                res.Else(
                    res.ifTrue[0].dst(0)
                )

        return res
