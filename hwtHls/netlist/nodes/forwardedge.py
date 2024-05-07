from typing import Optional, Union, List, Tuple, Generator

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.backedge import BACKEDGE_ALLOCATION_TYPE, HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import link_hls_nodes, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.typingFuture import override


class HlsNetNodeReadForwardedge(HlsNetNodeRead):
    """
    A read of data from loop enter block or from loop exit block.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dtype: HdlType, name: Optional[str]=None):
        HlsNetNodeRead.__init__(self, netlist, None, dtype=dtype, name=name)
        self.associatedWrite: Optional[HlsNetNodeWriteForwardedge] = None
        self.maxIosPerClk = 2  # read, write
        self._rtlIoAllocated = False
        self._rtlDataVldReg:Optional[Union[RtlSyncSignal, Interface]] = None

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNode", bool]:
        return HlsNetNodeReadBackedge.clone(self, memo, keepTopPortsConnected)

    def getAssociatedWrite(self):
        return self.associatedWrite

    @override
    def getSchedulingResourceType(self):
        return self

    @override
    def hasValidOnlyToPassFlags(self):
        return HlsNetNodeReadBackedge.hasValidOnlyToPassFlags(self)

    @override
    def hasReadyOnlyToPassFlags(self):
        return HlsNetNodeReadBackedge.hasReadyOnlyToPassFlags(self)

    def _rtlAllocDatapathIo(self):
        return HlsNetNodeReadBackedge._rtlAllocDatapathIo(self)

    def rtlAllocDataVldReg(self, allocator:"ArchElement"):
        return HlsNetNodeReadBackedge.rtlAllocDataVldReg(self, allocator)

    @override
    def rtlAlloc(self, allocator:"ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        return HlsNetNodeReadBackedge.rtlAlloc(self, allocator)


class HlsNetNodeWriteForwardedge(HlsNetNodeWrite):
    """
    Write for :class:`~.HlsNetNodeReadForwardedge`
    """

    def __init__(self, netlist:"HlsNetlistCtx", name:Optional[str]=None):
        HlsNetNodeWrite.__init__(self, netlist, None, name=name)
        self.associatedRead: Optional[HlsNetNodeReadForwardedge] = None
        self.maxIosPerClk = 2  # read, write
        self.allocationType = BACKEDGE_ALLOCATION_TYPE.BUFFER
        self.buffName = name
        self.channelInitValues = ()
        self._loopChannelGroup: Optional["LoopChanelGroup"] = None
        self._fullPort: Optional[HlsNetNodeOut] = None

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNode", bool]:
        return HlsNetNodeWriteBackedge.clone(self, memo, keepTopPortsConnected)

    def associateRead(self, r: HlsNetNodeReadForwardedge):
        assert isinstance(r, HlsNetNodeReadForwardedge), r
        r.associatedWrite = self
        self.associatedRead = r
        self.dst = r.src

    def getAssociatedWrite(self):
        return self

    def getFullPort(self) -> HlsNetNodeOut:
        return HlsNetNodeWriteBackedge.getFullPort(self)

    @override
    def getSchedulingResourceType(self):
        return self

    @staticmethod
    def createPredSucPair(netlist: "HlsNetlistCtx", name: str, srcV: HlsNetNodeOut)\
            ->Tuple["HlsNetNodeLoopDataWrite", HlsNetNodeReadForwardedge, HlsNetNodeOut]:
        r = HlsNetNodeReadForwardedge(netlist, srcV._dtype, name=name + "_dst")
        w = HlsNetNodeWriteForwardedge(netlist, name=name + "_src")
        link_hls_nodes(srcV, w._inputs[0])
        w.associateRead(r)
        link_hls_nodes(w.getOrderingOutPort(), r._addInput("orderingIn"))
        netlist.outputs.append(w)
        netlist.inputs.append(r)

        return w, r, r._outputs[0]

    @override
    def hasValidOnlyToPassFlags(self):
        return HlsNetNodeWriteBackedge.hasValidOnlyToPassFlags(self)

    @override
    def hasReadyOnlyToPassFlags(self):
        return HlsNetNodeWriteBackedge.hasReadyOnlyToPassFlags(self)

    def _getBufferCapacity(self):
        srcWrite = self
        clkPeriod = self.netlist.normalizedClkPeriod
        dstRead = self.associatedRead
        assert dstRead is not None
        dst_t = dstRead.scheduledOut[0]
        src_t = srcWrite.scheduledIn[0]
        assert src_t <= dst_t, ("This was supposed to be forward edge", self, src_t, dst_t)
        regCnt = indexOfClkPeriod(dst_t, clkPeriod) - indexOfClkPeriod(src_t, clkPeriod)
        assert regCnt >= 0, self
        return regCnt

    def _getRtlEnableForNonBufferReg(self, allocator: "ArchElement"):
        return HlsNetNodeWriteBackedge._getRtlEnableForNonBufferReg(self, allocator)

    def rtlAllocAsBuffer(self, allocator: "ArchElement", dstRead: HlsNetNodeReadForwardedge):
        return HlsNetNodeWriteBackedge.rtlAllocAsBuffer(self, allocator, dstRead)

    @override
    def rtlAlloc(self, allocator: "ArchElement"):
        self.associatedRead._rtlAllocDatapathIo()
        rtlObj = HlsNetNodeWriteBackedge.rtlAlloc(self, allocator)
        return rtlObj

    @override
    def debugIterShadowConnectionDst(self) -> Generator[Tuple[HlsNetNode, bool], None, None]:
        if self.associatedRead is not None:
            yield self.associatedRead, False
