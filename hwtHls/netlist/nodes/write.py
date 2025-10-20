from typing import Union, Optional, Generator, Callable

from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIOs.std import HwIOSignal
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.interfaceLevel.utils import HwIO_pack, \
    HwIO_connectPacked
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedulizationDict
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod


class HlsNetNodeWrite(HlsNetNodeExplicitSync):
    """
    :ivar dst: output interface not related to HLS
    :ivar associatedRead: if this write is part of internal channel this is a reference to read
        on the other part of the channel.
        
    :ivar _isBlocking: flag which specifies if this node is blocking or non-blocking write
    :ivar _mayBecomeFlushable: flag, if True the _isFlushable may be set to True
    :ivar _isFlushable: flag, if True the data may be transfered to destination even if
        parent sync node is stalling if dependencies are available
    #:ivar _mayFlushPort: the netlist input port, if it is 1 the node may perform write even
    #    if the parent node does not have ack. If parent did not have ack then isFlushed is set to 1
    #    to mark that the data was already flushed from parent it is not required to (and must not) write it it.
    #:ivar _isFlushedPort: the netlist out port with the status of isFlushed flag (explained in _mayFlushPort).
    :ivar _fullPort: :see: :meth:`~.HlsNetNodeWrite.getFullPort`
    
    :ivar buffName: name which can be used to override the name of the buffer in RTL
    :note: Flushing is required and may be set to True only if _rtlUseValid=True
    Flushing:
        * ready/valid for internal sync in node where this node is scheduled should use
        ready_forFlush/valid_forFlush
        * There is a register named flush which is 1 if the data was flushed to destination
        but this source node still has the data because parent sync node is stalling
        this flag is set it prevents setting valid for reader and marks reader ready as ignored
        * The flush flag is restarted if parent node stops stalling
        * mayFlush = src inputs valid & extraCond & ~skipWhen & dst.ready
          if this write writes channel dst.ready = dst.extraCond & ~dst.skipWhen & dst.parent.ack
    :ivar _bufferCapacity: an optional specification of the size of the buffer for this channel
        if None the size is infered from the scheduling
    """
    _PORT_ATTR_NAMES = HlsNetNodeExplicitSync._PORT_ATTR_NAMES + ["_portSrc"]

    def __init__(self, netlist: "HlsNetlistCtx",
                 ioProxy: "IoProxy",
                 dst: Union[RtlSignal, HwIO, None],
                 mayBecomeFlushable=False,
                 name:Optional[str]=None,
                 bufferCapacity:Optional[int]=None,
                 addSrcPort=True):
        HlsNetNode.__init__(self, netlist, name=name)
        self.ioProxy = ioProxy
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self.associatedRead: Optional[HlsNetNodeRead] = None
        self._initCommonPortProps(dst)
        self._portSrc: Optional[HlsNetNodeIn] = self._addInput("src") if addSrcPort else None
        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (HwIOSignal, RtlSignal)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp
        assert not indexCascade, ("There should not be any dst index, for indexed writes use :class:`~.HlsNetNodeWrite` node", dst, indexCascade)
        # assert isinstance(dst, (HlsNetNodeIn, HwIOStructRdVld, HwIOSignal, RtlSignalBase, HwIODataRdVld, HwIOStruct, HwIODataVld, HwIODataRd)), dst
        self.dst = dst
        self._isBlocking = True
        self._mayBecomeFlushable = mayBecomeFlushable
        self._isFlushable = False
        self._fullPort: Optional[HlsNetNodeOut] = None
        self.allocationType = CHANNEL_ALLOCATION_TYPE.BUFFER
        self._bufferCapacity = bufferCapacity
        self.buffName = None
        self._loopChannelGroup: Optional["LoopChanelGroup"] = None

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> list["HlsNetNode", bool]:
        y, isNew = HlsNetNodeExplicitSync.clone(self, memo, keepTopPortsConnected)
        if isNew:
            r = self.associatedRead
            if r is not None:
                y.associatedRead = r.clone(memo, True)

        return y, isNew

    def associateRead(self, read: HlsNetNodeRead):
        assert isinstance(read, HlsNetNodeRead), ("Can associate only with read of compatible type", read, self)
        read.associatedWrite = self
        self.associatedRead = read

    def getAssociatedWrite(self):
        return self

    def setNonBlocking(self):
        self._isBlocking = False

    def isForwardedge(self):
        r = self.associatedRead
        if r is None:
            return False

        assert self.scheduledZero is not None, ("Node must be scheduled to resolve this", self)
        assert r.scheduledZero is not None, ("Node must be scheduled to resolve this", r)
        return r.scheduledZero >= self.scheduledZero

    def isBackedge(self):
        return not self.isForwardedge()

    @override
    def _removeInput(self, index:int):
        src = self._portSrc
        if src is not None and src.in_i == index:
            self._portSrc = None

        forceEn = self._forceEnPort
        if forceEn is not None and forceEn.in_i == index:
            self._forceEnPort = None
        return HlsNetNodeExplicitSync._removeInput(self, index)

    def getSchedulingResourceType(self):
        resourceType = self.dst
        assert resourceType is not None, self
        return resourceType

    @override
    def checkScheduling(self):
        return HlsNetNodeRead.checkScheduling(self)

    @override
    def resetScheduling(self):
        return HlsNetNodeRead.resetScheduling(self)

    @override
    def setScheduling(self, schedule:SchedulizationDict):
        return HlsNetNodeRead.setScheduling(self, schedule)

    @override
    def moveSchedulingTime(self, offset:int):
        return HlsNetNodeRead.moveSchedulingTime(self, offset)

    @override
    def scheduleAsap(self, pathForDebug: Optional[SetList["HlsNetNode"]], beginOfFirstClk: int,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> list[int]:
        assert self.dependsOn, self
        return HlsNetNodeRead.scheduleAsap(self, pathForDebug, beginOfFirstClk, outputTimeGetter, isRead=False)

    @override
    def scheduleAlapCompaction(self,
                               endOfLastClk:int,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]):
        return HlsNetNodeRead.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter, excludeNode, isRead=False)

    def _getBufferCapacity(self):
        srcWrite = self
        clkPeriod = self.netlist.normalizedClkPeriod
        dstRead = self.associatedRead
        if dstRead is None or self.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE:
            return 0

        dstTime = dstRead.scheduledOut[0]
        srcTime = srcWrite.scheduledIn[0]
        assert srcTime <= dstTime, ("This was supposed to be forward edge", self, srcTime, dstTime)
        regCnt = indexOfClkPeriod(dstTime, clkPeriod) - indexOfClkPeriod(srcTime, clkPeriod)
        assert regCnt >= 0, self
        return regCnt

    def _shouldUseReadValidNBInsteadOfFullPort(self):
        """
        :returns: True if associatedRead.validNB is equal to fullPort and should be used instead
        """
        return self.associatedRead is not None and\
             self.allocationType != CHANNEL_ALLOCATION_TYPE.REG and\
             self._getBufferCapacity() == 1

    def setFlushable(self, enable:bool=True):
        if enable:
            assert not self._isFlushable, self
            assert self._mayBecomeFlushable, self
            assert self._rtlUseValid, self
            self._isFlushable = True
        else:

            self._isFlushable = False

    def getFullPort(self) -> HlsNetNodeOut:
        """
        The full port is HlsNetlistOut. Only usable for channels with capacity>0.
        * 1 if internal buffer of this channel is full.
        * empty = ~read.valid

        :attention: This port should be used only after scheduling to access internal state of the buffer.
            Under normal scenario one should use ready/readyNB.
        :attention: For CHANNEL_ALLOCATION_TYPE.REG valid/validNB and full is set on write.
            After read the valid/validNB stays 1 but full is cleared.
            Write is blocked while full and is not affected by valid/validNB.
            This is to avoid register duplication.
        :return: port which is 1 if there is a space in the buffer of this edge.
        """
        assert self.associatedRead is not None, ("This port should be used only for internal channels", self)
        assert self.scheduledZero is not None, ("This port should be used only after scheduling", self)
        assert self._getBufferCapacity() > 0, (
            "If this edge is not buffer this port should not be used, because it is const 0", self)
        full = self._fullPort
        if full is None:
            full = self._fullPort = self._addOutput(BIT, "full", addDefaultScheduling=True,
                                                    # = at the begin of clock where this write is
                                                    outputClkTickOffset=-1,
                                                    outputWireDelay=self.netlist.normalizedClkPeriod + self.netlist.scheduler.epsilon)
        return full

    def getForceEnPort(self) -> HlsNetNodeIn:
        """
        :attention: This port should be used only after scheduling to access internal state of the buffer for channels.
            Under normal scenario one should use ready/readyNB.
        :return: A port which can override register load enable to load input data even without presence of valid
            from parent element or ready from destination. The data is written in FIFO order, the first one is potentially lost, new data is appended.
            If the capacity is 0 this port has no meaning.
        """
        assert self.associatedRead is not None, ("This port should be used only for internal channels", self)
        assert self._getBufferCapacity() > 0, (
            "If this edge is not buffer this port should not be used, because it would do nothing", self)
        return HlsNetNodeExplicitSync.getForceEnPort(self)

    def _getRtlSyncTuple(self):
        return self.ioProxy._getRtlSyncTuple(self.dst)

    def _getRtlSyncSignals(self):
        return self.ioProxy._getRtlSyncSignals(self.dst)

    def _rtlAllocReadyPorts(self, allocator: "ArchElement"):
        readyRtl = self._getRtlSyncTuple()[1]
        if isinstance(readyRtl, int):
            raise NotImplementedError("rtl ready should not be requested because it is constant", self)

        if self.hasReady():
            allocator.rtlRegisterOutputRtlSignal(self._ready, readyRtl, False, False, True)

        if self.hasReadyNB():
            allocator.rtlRegisterOutputRtlSignal(self._readyNB, readyRtl, False, False, True)

    def _rtlAlloc_assignToSequenceOfRtlSignal(self, dst: Union[HwIOArray, tuple], src: RtlSignal, offset: int, rtlObj: list[HdlAssignmentContainer]):
        for dstItem in dst:
            if isinstance(dstItem, (HwIOArray, tuple)):
                offset = self._rtlAlloc_assignToSequenceOfRtlSignal(dstItem, src, offset, rtlObj)
            else:
                w = dstItem._dtype.bit_length()
                if w == 1:
                    _src = src[offset]
                else:
                    _src = src[w + offset:offset]
                offset += w
                rtlObj.append(dstItem(_src))

        return offset

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> list[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert not self._isRtlAllocated, self
        assert len(self.dependsOn) >= 1, (self, self.dependsOn)

        # apply indexes before assignments
        dep = self.dependsOn[0]
        assert dep is not None, self
        assert self.skipWhen is None, ("This port should be already lowered by RtlArchPassSyncLower", self)
        assert self._forceEnPort is None, ("This port should be already lowered by RtlArchPassSyncLower", self)

        if self.hasValid() or self.hasValidNB():
            raise AssertionError("Valid of write is always 1 and this port should be already optimized out")

        if self.hasAnyUsedReadyPort():
            self._rtlAllocReadyPorts(allocator)

        _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, self.scheduledIn[0])

        dst = self.dst
        if dst is None:
            if self.associatedRead is not None:
                self.associatedRead._rtlAllocDatapathIo()
                dst = self.dst

        if HdlType_isVoid(dep._dtype):
            # assert isinstance(_o, list) and not _o, _o
            rtlObj = []
        else:
            assert dst is not None, ("dst io port should be specified or resolved", self)
            exclude = self._getRtlSyncSignals()
            if isinstance(_o.data, HwIOStruct):
                rtlObj = dst(_o.data, exclude=exclude)
            elif isinstance(_o.data, RtlSignal) and isinstance(dst, RtlSignal):
                rtlObj = dst(_o.data)
            elif isinstance(dst, RtlSignal):
                if isinstance(dst._dtype, HStruct):
                    rtlObj = dst(HwIO_pack(_o.data, exclude=exclude))
                else:
                    rtlObj = dst(_o.data)
            elif isinstance(dst, (HwIOArray, tuple)):
                rtlObj = []
                self._rtlAlloc_assignToSequenceOfRtlSignal(dst, _o.data, 0, rtlObj)
            else:
                rtlObj = HwIO_connectPacked(_o.data, dst, exclude=exclude)

        # allocator.netNodeToRtl[o] = rtlObj
        if not isinstance(rtlObj, (list, tuple)):
            rtlObj = [rtlObj, ]
        allocator.netNodeToRtl[(dep, dst)] = rtlObj
        clkI = indexOfClkPeriod(self.scheduledIn[0], allocator.netlist.normalizedClkPeriod)
        if dst is None:
            rtlVldSignal = None
        else:
            rtlVldSignal, _ = self._getRtlSyncTuple()
            if rtlVldSignal == 1:
                rtlVldSignal = None
        allocator.rtlAllocDatapathWrite(self, rtlVldSignal, allocator.connections[clkI], rtlObj)

        # [0] - data, [1:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            assert sync is not None, ("Unconnected input port", self)
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if not HdlType_isVoid(sync._dtype):
                allocator.rtlAllocHlsNetNodeOutInTime(sync, t)

        self._isRtlAllocated = True
        return rtlObj

    def _getInterfaceName(self, io: Union[HwIO, list[HwIO]]) -> str:
        return HlsNetNodeRead._getInterfaceName(self, io)

    def __repr__(self, minify=False):
        src = self.dependsOn[0]
        allocationType = self.allocationType
        if allocationType != CHANNEL_ALLOCATION_TYPE.BUFFER:
            allocationType = " " + allocationType.name
        else:
            allocationType = ""

        dstName = "<None>" if self.dst is None else self._getInterfaceName(self.dst)
        if minify:
            return (
                f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''}"
                f"{allocationType:s} {self._stringFormatRtlUseReadyAndValid():s} {dstName:s}>"
            )
        else:
            if src is None:
                _src = "<None>"
            else:
                _src = f"{src.obj._id:d}:{src.out_i:d}" if isinstance(src, HlsNetNodeOut) else repr(src)
            return (
                f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''}"
                f"{allocationType:s} {self._stringFormatRtlUseReadyAndValid():s} {dstName:s} <- {_src:s}>"
            )

    @override
    def debugIterShadowConnectionDst(self) -> Generator[tuple[HlsNetNode, bool], None, None]:
        if self.associatedRead is not None:
            yield self.associatedRead, False
