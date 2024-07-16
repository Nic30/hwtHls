from typing import Union, Optional, List, Generator, Tuple

from hwt.code import If
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIOs.std import HwIOSignal
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.interfaceLevel.utils import HwIO_pack, \
    HwIO_connectPacked
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.syncUtils import HwIO_getSyncSignals, \
    HwIO_getSyncTuple
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead, HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.schedulableNode import OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedulizationDict
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, \
    timeUntilClkEnd
from hwtHls.ssa.value import SsaValue


class HlsNetNodeWrite(HlsNetNodeExplicitSync):
    """
    :ivar dst: output interface not related to HLS
    :ivar channelInitValues: Optional tuple for value initialization.
        (used only if this node is connected to internal channel)
    :ivar associatedRead: if this write is part of internal channel this is a reference to read
        on the other part of the channel.
        
    :ivar _isBlocking: flag which specifies if this node is blocking or non-blocking write

    :ivar _mayBecomeFlushable: flag, if True the _isFlushable may be set to True
    :ivar _isFlushable: flag, if True the data may be transfered to destination even if
        parent sync node is stalling if dependencies are available
    :ivar _mayFlushPort: the netlist input port, if it is 1 the node may perform write even
        if the parent node does not have ack. If parent did not have ack then isFlushed is set to 1
        to mark that the data was already flushed from parent it is not required to (and must not) write it it.
    :ivar _isFlushedPort: the netlist out port with the status of isFlushed flag (explained in _mayFlushPort).
    :ivar _fullPort: :see: :meth:`~.HlsNetNodeWrite.getFullPort`
    :ivar _forceWritePort: :see: :meth:`~.HlsNetNodeWrite.getForceWritePort`
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
    """
    _PORT_ATTR_NAMES = HlsNetNodeExplicitSync._PORT_ATTR_NAMES + ["_mayFlushPort", "_isFlushedPort", "_portSrc"]

    def __init__(self, netlist: "HlsNetlistCtx",
                 dst: Union[RtlSignal, HwIO, SsaValue, None],
                 mayBecomeFlushable=False,
                 name:Optional[str]=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self.associatedRead: Optional[HlsNetNodeRead] = None
        self._initCommonPortProps(dst)
        self._portSrc: HlsNetNodeIn = self._addInput("src")
        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (HwIOSignal, RtlSignal)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp
        assert not indexCascade, ("There should not be any dst index, for indexed writes use :class:`~.HlsNetNodeWrite` node", dst, indexCascade)
        # assert isinstance(dst, (HlsNetNodeIn, HwIOStructRdVld, HwIOSignal, RtlSignalBase, HwIODataRdVld, HwIOStruct, HwIODataVld, HwIODataRd)), dst
        self.dst = dst
        self.maxIosPerClk: int = 1
        self._isBlocking = True
        self._mayBecomeFlushable = mayBecomeFlushable
        self._isFlushable = False
        self._rtlReady_forFlush: Optional[RtlSignal] = None
        self._rtlValid_forFlush: Optional[RtlSignal] = None
        self._mayFlushPort: Optional[HlsNetNodeIn] = None
        self._isFlushedPort: Optional[HlsNetNodeOut] = None
        self._fullPort: Optional[HlsNetNodeOut] = None
        self._forceWritePort: Optional[HlsNetNodeIn] = None
        self.channelInitValues = ()

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
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
        if src.in_i == index:
            self._portSrc = None
        mayFlush = self._mayFlushPort
        if mayFlush is not None and mayFlush.in_i == index:
            self._mayFlushPort = None
        return HlsNetNodeExplicitSync._removeInput(self, index)

    @override
    def _removeOutput(self, index:int):
        isFlushed = self._isFlushedPort
        if isFlushed is not None and isFlushed.out_i == index:
            self._isFlushedPort = None
        return HlsNetNodeExplicitSync._removeOutput(self, index)

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
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        assert self.dependsOn, self
        return HlsNetNodeRead.scheduleAsap(self, pathForDebug, beginOfFirstClk, outputTimeGetter)

    @override
    def scheduleAlapCompaction(self, endOfLastClk:int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        return HlsNetNodeRead.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter)

    def _getBufferCapacity(self):
        srcWrite = self
        clkPeriod = self.netlist.normalizedClkPeriod
        dstRead = self.associatedRead
        if dstRead is None:
            return 0
        dstTime = dstRead.scheduledOut[0]
        srcTime = srcWrite.scheduledIn[0]
        assert srcTime <= dstTime, ("This was supposed to be forward edge", self, srcTime, dstTime)
        regCnt = indexOfClkPeriod(dstTime, clkPeriod) - indexOfClkPeriod(srcTime, clkPeriod)
        assert regCnt >= 0, self
        return regCnt

    def setFlushable(self, enable:bool=True):
        if enable:
            assert not self._isFlushable, self
            assert self._mayBecomeFlushable, self
            assert self._rtlUseValid, self
            self._isFlushable = True
            timeUntilClkEndFromZero = timeUntilClkEnd(self.scheduledZero, self.netlist.normalizedClkPeriod)
            timeUntilClkEndFromZero -= self.netlist.scheduler.epsilon
            self._mayFlushPort = self._addInput("mayFlush", addDefaultScheduling=True, inputWireDelay=-timeUntilClkEndFromZero)
        else:
            assert self._isFlushable, self
            assert self.dependsOn[self._mayFlushPort.in_i] is None, self
            self._removeInput(self._mayFlushPort.in_i)
            isFlushedPort = self._isFlushedPort
            if isFlushedPort is not None:
                assert not self.usedBy[isFlushedPort.out_i], self
                self._removeOutput(isFlushedPort.out_i)
            self._isFlushable = False

    def getIsFlushedPort(self) -> HlsNetNodeOut:
        f = self._isFlushedPort
        if f is None:
            assert self._isFlushable
            f = self._isFlushedPort = self._addOutput(BIT, "isFlushed", addDefaultScheduling=True)
        return f

    def getFullPort(self) -> HlsNetNodeOut:
        """
        The full port is HlsNetlistOut. Only usable for channels with capacity>0.
        * 1 if internal buffer of this channel is full.
        * empty = ~read.valid

        :attention: This port should be used only after scheduling to access internal state of the buffer.
            Under normal scenario one should use ready/readyNB.
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

    def getForceWritePort(self) -> HlsNetNodeIn:
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
        forceWrite = self._forceWritePort
        if forceWrite is None:
            netlist = self.netlist
            forceWrite = self._forceWritePort = self._addInput("forceWrite", addDefaultScheduling=True,
                                                    # = at the end of clock where this write is
                                                    inputClkTickOffset=0,
                                                    inputWireDelay=netlist.normalizedClkPeriod - self.scheduledZero - netlist.scheduler.epsilon)
        return forceWrite

    def getRtlFlushReadyValidSignal(self):
        selfName = self.name if self.name else f'{self.netlist.namePrefix}n{self._id}'
        if self._rtlUseReady:
            if self._rtlReady_forFlush is None:
                self._rtlReady_forFlush = self.netlist.parentHwModule._sig(f"{selfName}_ready_forFlush", BIT, nop_val=0)
        # valid is always needed because we need to detect when write is performed to reset isFlushed register
        if self._rtlValid_forFlush is None:
            self._rtlValid_forFlush = self.netlist.parentHwModule._sig(f"{selfName}_valid_forFlush", BIT, nop_val=0)

        return self._rtlReady_forFlush, self._rtlValid_forFlush

    @override
    def getAllocatedRTL(self, allocator: "ArchElement"):
        assert self._isRtlAllocated, self
        dst = self.dst
        dep = self.dependsOn[0]
        return allocator.netNodeToRtl[(dep, dst)]

    def _rtlAllocReadyPorts(self, allocator: "ArchElement"):
        readyRtl = HwIO_getSyncTuple(self.dst)[1]
        if isinstance(readyRtl, int):
            raise NotImplementedError("rtl ready should not be requested because it is constant", self)

        # if self._isFlushable:
        #    mayFlushI = self._mayFlushPort.in_i
        #    mayFlush = allocator.rtlAllocHlsNetNodeOutInTime(self.dependsOn[mayFlushI], self.scheduledIn[mayFlushI])
        #    readyRtl = readyRtl | mayFlush.data

        if self.hasReady():
            allocator.rtlRegisterOutputRtlSignal(self._ready, readyRtl, False, False, True)

        if self.hasReadyNB():
            allocator.rtlRegisterOutputRtlSignal(self._readyNB, readyRtl, False, False, True)

    def _rtlAllocIsFlushedReg(self, allocator: "ArchElement"):
        mayFlush = allocator.rtlAllocHlsNetNodeInDriverIfExists(self._mayFlushPort).data
        extraCond = allocator.rtlAllocHlsNetNodeInDriverIfExists(self.extraCond)
        if extraCond is not None:
            mayFlush = mayFlush & extraCond.data
        skipWhen = allocator.rtlAllocHlsNetNodeInDriverIfExists(self.skipWhen)
        if skipWhen is not None:
            mayFlush = mayFlush & ~skipWhen.data
        isFlushed = allocator._reg(f"{self.netlist.namePrefix}n{self._id}_isFlushed", def_val=0)
        if self._isFlushedPort is not None:
            allocator.rtlRegisterOutputRtlSignal(self._isFlushedPort, isFlushed, True, False, True)

        valid, ready = HwIO_getSyncTuple(self.dst)
        if not self._rtlUseReady:
            # if there is no RTL ready signal we can use ack of stage where read from this channel is
            # and read flags or IO does not use any ready and thus ready=1
            ready = 1
        readyForFlush, validForFlush = self.getRtlFlushReadyValidSignal()
        assert validForFlush is not None
        If(validForFlush,
           isFlushed(0)
        ).Elif(mayFlush & ready,
           isFlushed(1)
        )
        if self._rtlUseValid:
            valid(~isFlushed & mayFlush)

        if self._rtlUseReady:
            readyForFlush(isFlushed | ready)
        else:
            assert readyForFlush is None, self

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> List[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert not self._isRtlAllocated, self
        assert len(self.dependsOn) >= 1, (self, self.dependsOn)

        # apply indexes before assignments
        dst = self.dst
        dep = self.dependsOn[0]
        assert dep is not None, self

        # [0] - data, [1:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            assert sync is not None, ("Unconnected input port", self)
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if not HdlType_isVoid(sync._dtype):
                allocator.rtlAllocHlsNetNodeOutInTime(sync, t)

        if self.hasValid() or self.hasValidNB():
            raise AssertionError("Valid of write is always 1 and this port should be already optimized out")

        if self._isFlushable:
            self._rtlAllocIsFlushedReg(allocator)

        if self.hasAnyUsedReadyPort():
            self._rtlAllocReadyPorts(allocator)

        _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, self.scheduledIn[0])

        if HdlType_isVoid(dep._dtype):
            # assert isinstance(_o, list) and not _o, _o
            rtlObj = []
        else:
            exclude = HwIO_getSyncSignals(dst)
            if isinstance(_o.data, HwIOStruct):
                rtlObj = dst(_o.data, exclude=exclude)
            elif isinstance(_o.data, RtlSignal) and isinstance(dst, RtlSignal):
                rtlObj = dst(_o.data)
            elif isinstance(dst, RtlSignal):
                if isinstance(dst._dtype, HStruct):
                    rtlObj = dst(HwIO_pack(_o.data, exclude=exclude))
                else:
                    rtlObj = dst(_o.data)
            else:
                rtlObj = HwIO_connectPacked(_o.data, dst, exclude=exclude)

        # allocator.netNodeToRtl[o] = rtlObj
        if not isinstance(rtlObj, (list, tuple)):
            rtlObj = [rtlObj, ]
        allocator.netNodeToRtl[(dep, dst)] = rtlObj
        clkI = indexOfClkPeriod(self.scheduledIn[0], allocator.netlist.normalizedClkPeriod)
        allocator.rtlAllocDatapathWrite(self, allocator.connections[clkI], rtlObj)

        self._isRtlAllocated = True
        return rtlObj

    def _getInterfaceName(self, io: Union[HwIO, Tuple[HwIO]]) -> str:
        return HlsNetNodeRead._getInterfaceName(self, io)

    def _stringFormatRtlUseReadyAndValid(self):
        return HlsNetNodeRead._stringFormatRtlUseReadyAndValid(self)

    def __repr__(self, minify=False):
        src = self.dependsOn[0]
        allocationType = getattr(self, "allocationType", None)
        if allocationType:
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
    def debugIterShadowConnectionDst(self) -> Generator[Tuple[HlsNetNode, bool], None, None]:
        if self.associatedRead is not None:
            yield self.associatedRead, False


class HlsNetNodeWriteIndexed(HlsNetNodeWrite):
    """
    Same as :class:`~.HlsNetNodeWrite` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dst:Union[RtlSignal, HwIO, SsaValue]):
        HlsNetNodeWrite.__init__(self, netlist, dst)
        self.indexes = [self._addInput("index0"), ]

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeWrite.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y.indexes = [y._inputs[i.in_i] for i in self.indexes]

        return y, isNew

    @override
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        allNonOrdering = (self._inputs[0], self.extraCond, self.skipWhen, self._inputOfCluster, self._outputOfCluster, *self.indexes)
        for i in self._inputs:
            if i not in allNonOrdering:
                yield i

    def __repr__(self, minify=False):
        src = self.src
        if src is NOT_SPECIFIED:
            src = self.dependsOn[0]
        dstName = self._getInterfaceName(self.dst)
        if minify:
            return (f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''}"
                f" {self._stringFormatRtlUseReadyAndValid():s} {dstName}>")
        else:
            return (
                f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''}"
                f" {self._stringFormatRtlUseReadyAndValid():s} {dstName}{HlsNetNodeReadIndexed._strFormatIndexes(self.indexes)} <- {src} >"
            )
