from typing import Optional, Union, List, Tuple, Generator

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.backedge import BACKEDGE_ALLOCATION_TYPE, HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import link_hls_nodes, HlsNetNodeOut, \
    HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class HlsNetNodeReadForwardedge(HlsNetNodeRead):
    """
    A read of data from loop enter block or from loop exit block.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dtype: HdlType, name: Optional[str]=None):
        HlsNetNodeRead.__init__(self, netlist, None, dtype=dtype, name=name)
        self.associatedWrite: Optional[HlsNetNodeWriteForwardedge] = None
        self.maxIosPerClk = 2  # read, write
        self._rtlIoAllocated = False
        self._rtlDataVldReg:Optional[Union[RtlSyncSignal, HwIO]] = None

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
    _PORT_ATTR_NAMES = HlsNetNodeWrite._PORT_ATTR_NAMES + ["_fullPort"]

    def __init__(self, netlist:"HlsNetlistCtx", mayBecomeFlushable=False, name:Optional[str]=None):
        HlsNetNodeWrite.__init__(self, netlist, None, mayBecomeFlushable=mayBecomeFlushable, name=name)
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

    @override
    def associateRead(self, r: HlsNetNodeReadForwardedge):
        super().associateRead(r)
        self.dst = r.src

    @override
    def isForwardedge(self):
        return True

    @override
    def isBackedge(self):
        return False

    def getFullPort(self) -> HlsNetNodeOut:
        return HlsNetNodeWriteBackedge.getFullPort(self)

    def getForceWritePort(self) -> HlsNetNodeIn:
        return HlsNetNodeWriteBackedge.getForceWritePort(self)

    @override
    def getSchedulingResourceType(self):
        return self

    @staticmethod
    def createPredSucPair(netlist: "HlsNetlistCtx", name: str, srcV: HlsNetNodeOut)\
            ->Tuple["HlsNetNodeLoopDataWrite", HlsNetNodeReadForwardedge, HlsNetNodeOut]:
        r = HlsNetNodeReadForwardedge(netlist, srcV._dtype, name=name + "_dst")
        w = HlsNetNodeWriteForwardedge(netlist, name=name + "_src")
        link_hls_nodes(srcV, w._portSrc)
        w.associateRead(r)
        link_hls_nodes(w.getOrderingOutPort(), r._addInput("orderingIn"))
        netlist.outputs.append(w)
        netlist.inputs.append(r)

        return w, r, r._portDataOut

    @override
    def hasValidOnlyToPassFlags(self):
        return HlsNetNodeWriteBackedge.hasValidOnlyToPassFlags(self)

    @override
    def hasReadyOnlyToPassFlags(self):
        return HlsNetNodeWriteBackedge.hasReadyOnlyToPassFlags(self)

    def _getRtlEnableForNonBufferReg(self, allocator: "ArchElement"):
        return HlsNetNodeWriteBackedge._getRtlEnableForNonBufferReg(self, allocator)

    def rtlAllocAsBuffer(self, allocator: "ArchElement", dstRead: HlsNetNodeReadForwardedge):
        return HlsNetNodeWriteBackedge.rtlAllocAsBuffer(self, allocator, dstRead)

    @override
    def rtlAlloc(self, allocator: "ArchElement"):
        return HlsNetNodeWriteBackedge.rtlAlloc(self, allocator)

