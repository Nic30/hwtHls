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
from hwtHls.netlist.nodes.explicitSync import createOrderingLink
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.frontend.ioProxyScalar import IoProxyScalar


class HlsNetNodeReadForwardedge(HlsNetNodeRead):
    """
    A read of data from loop enter block or from loop exit block.
    """

    def __init__(self, netlist:"HlsNetlistCtx", ioProxy: IoProxyScalar, dtype: HdlType, name: Optional[str]=None, channelInitValues=()):
        HlsNetNodeRead.__init__(self, netlist, ioProxy, None, dtype=dtype, name=name, channelInitValues=channelInitValues)
        self.associatedWrite: Optional[HlsNetNodeWriteForwardedge]
        self._rtlDataVldReg:Optional[Union[RtlSignal, HwIO]] = None
        self._rtlFullReg:Optional[Union[RtlSignal, HwIO]] = None

    @classmethod
    def _constructorAsHlsNetNodeRead(cls, netlist: "HlsNetlistCtx", ioProxy: IoProxyScalar, src: Union[RtlSignal, HwIO, None],
                 dtype: Optional[HdlType]=None, name:Optional[str]=None, channelInitValues=(), addPortDataOut=True):
        assert dtype is not None
        assert addPortDataOut
        # assert src is None, src
        n = cls(netlist, ioProxy, dtype, name=name, channelInitValues=channelInitValues)
        n.src = src
        return n

    @override
    def getSchedulingResourceType(self):
        # edges are asserted to be unique read/write pairs
        return None

    def _rtlAllocDatapathIo(self):
        return HlsNetNodeReadBackedge._rtlAllocDatapathIo(self)

    def rtlAllocDataVldAndFullReg(self, allocator:"ArchElement"):
        return HlsNetNodeReadBackedge.rtlAllocDataVldAndFullReg(self, allocator)

    def _mayHappenConcurrentlyWithWrite(self):
        return HlsNetNodeReadBackedge._mayHappenConcurrentlyWithWrite(self)

    @override
    def rtlAlloc(self, allocator:"ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        return HlsNetNodeReadBackedge.rtlAlloc(self, allocator)


class HlsNetNodeWriteForwardedge(HlsNetNodeWrite):
    """
    Write for :class:`~.HlsNetNodeReadForwardedge`
    """
    _PORT_ATTR_NAMES = HlsNetNodeWrite._PORT_ATTR_NAMES + ["_fullPort"]

    def __init__(self, netlist:"HlsNetlistCtx", ioProxy: IoProxyScalar, mayBecomeFlushable=False, bufferCapacity:Optional[int]=None, name:Optional[str]=None):
        HlsNetNodeWrite.__init__(self, netlist, ioProxy, None, mayBecomeFlushable=mayBecomeFlushable, bufferCapacity=bufferCapacity, name=name)
        self.associatedRead: Optional[HlsNetNodeReadForwardedge]

    @override
    def _getBufferCapacity(self) -> int:
        if self._bufferCapacity is not None:
            assert self.associatedRead is not None
            if self.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE:
                assert self._bufferCapacity == 0, self
            return self._bufferCapacity

        return HlsNetNodeWrite._getBufferCapacity(self)

    @classmethod
    def _constructorAsHlsNetNodeWrite(cls, netlist: "HlsNetlistCtx",
                 ioProxy: IoProxyScalar,
                 dst: Union[RtlSignal, HwIO, None],
                 mayBecomeFlushable=False,
                 bufferCapacity:Optional[int]=None,
                 name:Optional[str]=None,
                 addSrcPort=True):
        assert addSrcPort
        #assert dst is None, dst
        n = cls(netlist, ioProxy, mayBecomeFlushable=mayBecomeFlushable, bufferCapacity=bufferCapacity, name=name)
        n.dst = dst
        return n

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
        ioProxy = IoProxyScalar(None, None, dtype=srcV._dtype)
        r = HlsNetNodeReadForwardedge(netlist, ioProxy, srcV._dtype, name=name + "_dst")
        w = HlsNetNodeWriteForwardedge(netlist, ioProxy, name=name + "_src")
        parentForRead.addNode(r)
        parentForWrite.addNode(w)
        srcV.connectHlsIn(w._portSrc)
        w.associateRead(r)
        createOrderingLink(w, r)

        return w, r, r._portDataOut

    def _rtlAllocAsBuffer(self, allocator: "ArchElement", dstRead: HlsNetNodeReadForwardedge):
        return HlsNetNodeWriteBackedge._rtlAllocAsBuffer(self, allocator, dstRead)

    def _rtlAllocAsRegOrImmediate(self, allocator: "ArchElement", dstRead: HlsNetNodeReadForwardedge):
        return HlsNetNodeWriteBackedge._rtlAllocAsRegOrImmediate(self, allocator, dstRead)

    @override
    def rtlAlloc(self, allocator: "ArchElement"):
        return HlsNetNodeWriteBackedge.rtlAlloc(self, allocator)

