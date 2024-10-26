from typing import Optional, Union, List, Tuple, Callable

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class HlsNetNodeReadForwardedge(HlsNetNodeRead):
    """
    A read of data from loop enter block or from loop exit block.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dtype: HdlType, name: Optional[str]=None, channelInitValues=()):
        HlsNetNodeRead.__init__(self, netlist, None, dtype=dtype, name=name, channelInitValues=channelInitValues)
        self.associatedWrite: Optional[HlsNetNodeWriteForwardedge] = None
        self._rtlDataVldReg:Optional[Union[RtlSignal, HwIO]] = None

    @override
    def getSchedulingResourceType(self):
        # edges are asserted to be unique read/write pairs
        return None

    def _rtlAllocDatapathIo(self):
        return HlsNetNodeReadBackedge._rtlAllocDatapathIo(self)

    def rtlAllocDataVldAndFullReg(self, allocator:"ArchElement"):
        return HlsNetNodeReadBackedge.rtlAllocDataVldAndFullReg(self, allocator)

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
        self.associatedRead: Optional[HlsNetNodeReadForwardedge]
        self._loopChannelGroup: Optional["LoopChanelGroup"] = None

    @override
    def getSchedulingResourceType(self):
        # edges are asserted to be unique read/write pairs
        return None

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNode", bool]:
        return HlsNetNodeWriteBackedge.clone(self, memo, keepTopPortsConnected)

    def _rtlAllocRegisterReadySignal(self, allocator: "ArchElement", readySignalGetter: Callable[[], RtlSignal]):
        return HlsNetNodeWriteBackedge._rtlAllocRegisterReadySignal(self, allocator, readySignalGetter)

    def _rtlAllocRegisterFullSignal(self, allocator: "ArchElement", full: RtlSignal):
        return HlsNetNodeWriteBackedge._rtlAllocRegisterFullSignal(self, allocator, full)

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

    @staticmethod
    def createPredSucPair(netlist: "HlsNetlistCtx",
                          parentForWrite:"ArchElement",
                          parentForRead: "ArchElement",
                          name: str, srcV: HlsNetNodeOut)\
            ->Tuple["HlsNetNodeLoopDataWrite", HlsNetNodeReadForwardedge, HlsNetNodeOut]:
        r = HlsNetNodeReadForwardedge(netlist, srcV._dtype, name=name + "_dst")
        w = HlsNetNodeWriteForwardedge(netlist, name=name + "_src")
        parentForRead.addNode(r)
        parentForWrite.addNode(w)
        srcV.connectHlsIn(w._portSrc)
        w.associateRead(r)
        w.getOrderingOutPort().connectHlsIn(r._addInput("orderingIn"))

        return w, r, r._portDataOut

    def _rtlAllocAsBuffer(self, allocator: "ArchElement", dstRead: HlsNetNodeReadForwardedge):
        return HlsNetNodeWriteBackedge._rtlAllocAsBuffer(self, allocator, dstRead)

    @override
    def rtlAlloc(self, allocator: "ArchElement"):
        return HlsNetNodeWriteBackedge.rtlAlloc(self, allocator)

