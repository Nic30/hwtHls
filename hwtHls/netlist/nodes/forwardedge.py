from typing import Optional, Union, List, Tuple, Generator

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import HandshakeSync
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.backedge import BACKEDGE_ALLOCATION_TYPE, HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.orderable import HdlType_isVoid
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod


class HlsNetNodeReadForwardedge(HlsNetNodeRead):
    """
    A read of data from loop enter block or from loop exit block.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dtype: HdlType, name: Optional[str]=None):
        if HdlType_isVoid(dtype):
            src = HandshakeSync()
        else:
            src = HsStructIntf()
            src.T = dtype
        src._name = name
        HlsNetNodeRead.__init__(self, netlist, src, dtype=dtype, name=name)
        self.associatedWrite: Optional[HlsNetNodeWriteForwardedge] = None
        self._rtlIoAllocated = False
        self.maxIosPerClk = 2
        self._rtlIoAllocated = False

    def _getSchedulingResourceType(self):
        return self

    def _allocateRtlIo(self):
        return HlsNetNodeReadBackedge._allocateRtlIo(self)

    def allocateRtlInstance(self, allocator:"ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        self._allocateRtlIo()
        return HlsNetNodeRead.allocateRtlInstance(self, allocator)


class HlsNetNodeWriteForwardedge(HlsNetNodeWrite):
    """
    Write for :class:`~.HlsNetNodeReadForwardedge`
    """

    def __init__(self, netlist:"HlsNetlistCtx", name:Optional[str]=None):
        HlsNetNodeWrite.__init__(self, netlist, None, None, name=name)
        self.associatedRead: Optional[HlsNetNodeReadForwardedge] = None
        self.maxIosPerClk = 2
        self.allocationType = BACKEDGE_ALLOCATION_TYPE.BUFFER
        self.buffName = name
        self.channelInitValues = ()
        self._loopChannelGroup: Optional["LoopChanelGroup"] = None

    def associateRead(self, r: HlsNetNodeReadForwardedge):
        assert isinstance(r, HlsNetNodeReadForwardedge), r
        r.associatedWrite = self
        self.associatedRead = r
        self.dst = r.src

    def _getSchedulingResourceType(self):
        return self

    @staticmethod
    def createPredSucPair(netlist: "HlsNetlistCtx", name: str, dtype: HdlType)\
            ->Tuple["HlsNetNodeLoopDataWrite", HlsNetNodeReadForwardedge]:
        r = HlsNetNodeReadForwardedge(netlist, dtype, name=name + "_dst")
        w = HlsNetNodeWriteForwardedge(netlist, name=name + "_src")
        w.associateRead(r)
        link_hls_nodes(w.getOrderingOutPort(), r._addInput("orderingIn"))
        netlist.outputs.append(w)
        netlist.inputs.append(r)

        return w, r

    def _getSizeOfBuffer(self, clkPeriod: SchedTime):
        srcWrite = self
        dstRead = self.associatedRead
        assert dstRead is not None
        dst_t = dstRead.scheduledOut[0]
        src_t = srcWrite.scheduledIn[0]
        # assert dst_t <= src_t, ("This was supposed to be backward edge", dst_t, src_t, srcWrite, dstRead)
        # 1 register at minimum, because we need to break a combinational path
        # the size of buffer is derived from the latency of operations between the io ports
        assert src_t <= dst_t, self
        # forward edge
        regCnt = indexOfClkPeriod(dst_t, clkPeriod) - indexOfClkPeriod(src_t, clkPeriod)
        assert regCnt >= 0, self
        return regCnt

    def allocateRtlInstance(self, allocator:"ArchElement"):
        self.associatedRead._allocateRtlIo()
        rtlObj = HlsNetNodeWriteBackedge.allocateRtlInstance(self, allocator)
        return rtlObj

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        yield self.associatedRead
