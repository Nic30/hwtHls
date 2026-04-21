from collections import deque
from itertools import zip_longest
from typing import Union, Optional, Generator, Callable

from hwt.code import If
from hwt.code_utils import rename_signal
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bitsConst import HBitsConst
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
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.frontend.ioProxyScalarHlsNetlistAgent import HlsNetlistSimAgentScalarChannelMonitor
from hwtHls.netlist.analysis.hlsNetlistSimAgent import HlsNetlistSimAgent
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedulizationDict
from hwtHls.netlist.scheduler.clk_math import clkWindowIndex
from hwtLib.handshaked.builder import HsBuilder


class HlsNetNodeWrite(HlsNetNodeExplicitSync):
    """
    The read from IO or HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.

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
    _PORT_ATTR_NAMES = HlsNetNodeExplicitSync._PORT_ATTR_NAMES + ["_portSrc", "_fullPort"]

    def __init__(self, netlist: "HlsNetlistCtx",
                 ioProxy: "IoProxy",
                 dst: Union[RtlSignal, HwIO, None],
                 mayBecomeFlushable=False,
                 name:Optional[str]=None,
                 bufferCapacity:Optional[int]=None,
                 isBlocking:bool=True,
                 isBackedge:bool=False,
                 addSrcPort=True):
        #if name is None and isinstance(dst, HwIO) and dst._name is not None:
        #    name = dst._name
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
        self._isBlocking = isBlocking
        self._isBackedge = isBackedge
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
            lcg = self._loopChannelGroup
            if lcg is not None:
                y._loopChannelGroup = lcg.clone()
        return y, isNew

    def associateRead(self, read: HlsNetNodeRead):
        assert isinstance(read, HlsNetNodeRead), ("Can associate only with read of compatible type", read, self)
        assert not self.rtlPortPhysicallyExits(), self
        assert self.dst is read.src, (self, read)
        read.associatedWrite = self
        self.associatedRead = read

    def getAssociatedWrite(self):
        return self

    def setNonBlocking(self):
        self._isBlocking = False

    def isChannel(self):
        return self.associatedRead is not None

    def isForwardedge(self):
        r = self.associatedRead
        if r is None:
            return False
        if self._isBackedge:
            return False
        if self.scheduledZero is not None:
            assert r.scheduledZero is not None, ("Node must be scheduled to resolve this", r)
            return r.scheduledZero >= self.scheduledZero
        return True

    def isBackedge(self):
        r = self.associatedRead
        if r is None:
            return False
        if not self._isBackedge:
            return False
        if  self.scheduledZero is not None:
            assert r.scheduledZero is not None, ("Node must be scheduled to resolve this", r)
            return r.scheduledZero <= self.scheduledZero
        return True

    @override
    def _removeInput(self, index:int):
        src = self._portSrc
        if src is not None and src.in_i == index:
            self._portSrc = None

        forceEn = self._forceEnPort
        if forceEn is not None and forceEn.in_i == index:
            self._forceEnPort = None

        return HlsNetNodeExplicitSync._removeInput(self, index)

    @override
    def _removeOutput(self, index:int):
        if self._fullPort is not None and self._fullPort.out_i == index:
            self._fullPort = None
        return HlsNetNodeExplicitSync._removeOutput(self, index)

    def getSchedulingResourceType(self):
        resourceType = self.dst
        if resourceType is None:
            return self
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
        if self._bufferCapacity is not None:
            assert self.associatedRead is not None, self
            if self.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE:
                assert self._bufferCapacity == 0, self
            return self._bufferCapacity

        srcWrite = self
        clkPeriod = self.netlist.normalizedClkPeriod
        dstRead = self.associatedRead
        if dstRead is None or self.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE:
            return 0
        elif self._isBackedge:
            return 1

        dstTime = dstRead.scheduledOut[0]
        srcTime = srcWrite.scheduledIn[0]
        assert srcTime <= dstTime, ("This was supposed to be forward edge", self, srcTime, dstTime)
        regCnt = clkWindowIndex(dstTime, clkPeriod) - clkWindowIndex(srcTime, clkPeriod)
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

    @override
    def hlsNetlistSimGetHandler(self, sim: "HlsNetlistSimulator") -> HlsNetlistSimAgentScalarChannelMonitor:
        if self.associatedRead is None:
            # top IO write
            proxy: "IoProxy" = self.ioProxy
            assert proxy is not None, self
            ag = sim.simAgentForIoProxy.get(proxy, None)
            if ag is None:
                argI, isOut = sim.topIoOrder[proxy]
                data = sim.topIoArgs[argI]
                if isOut:
                    ag: HlsNetlistSimAgent = proxy.getHlsNetlistSimAgentMonitor(data)
                else:
                    ag = proxy.getHlsNetlistSimAgentDriver(data)
                sim.simAgentForIoProxy[proxy] = ag
        else:
            # channel write
            data = sim.dataForChannel.get(self)
            if data is None:
                data = deque()
                sim.dataForChannel[self] = data
            initValues = self.associatedRead.channelInitValues
            if initValues:
                for v in initValues:
                    if len(v) == 0:
                        # channels without the data
                        data.append(None)
                    else:
                        assert len(v) == 1, v
                        assert isinstance(v, tuple) and isinstance(v[0], HBitsConst), v
                        data.append(v[0])

            ag = HlsNetlistSimAgentScalarChannelMonitor(self, data)
        return ag

    def rtlPortPhysicallyExits(self):
        dst = self.dst
        if dst is None:
            return False

        if isinstance(dst, HwIO) and dst._parent is None:
            return False

        return True

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

    def _rtlAllocRegisterReadySignal(self, allocator: "ArchElement", readySignalGetter: Callable[[], RtlSignal]):
        if self._rtlUseReady:
            if self._ready is not None or self._readyNB is not None:
                readySignal = readySignalGetter()
                for rdOut in (self._ready, self._readyNB):
                    if rdOut is None:
                        continue
                    allocator.rtlRegisterOutputRtlSignal(rdOut, readySignal, False, False, True)
        else:
            assert self._ready is None, ("If _rtlUseReady is False the the ready port should not be used because it is const 1", self)
            assert self._readyNB is None, ("If _rtlUseReady is False the the readyNB port should not be used because it is const 1", self)

    def _rtlAllocRegisterFullSignal(self, allocator: "ArchElement", full: RtlSignal):
        if self._fullPort is not None:
            assert full is not None, ("If node has full port it should also have a valid port", self)
            if allocator._dbgAddSignalNamesToSync:
                full = rename_signal(allocator, full, f"{self.name:s}_full")
            allocator.rtlRegisterOutputRtlSignal(self._fullPort, full, True, False, True)

    def _rtlAllocAsBuffer(self, allocator: "ArchElement", dstRead: HlsNetNodeRead):
        """
        :note: if the write is flushable the srcWrite.dst sync signals drivers are altered
            and the code of this function does not care about it
        """
        srcWrite = self
        dst = srcWrite.dst
        assert self.isChannel(), self
        res = self.rtlAllocAsIO(allocator)
        regCnt = self._getBufferCapacity()
        assert dst is not dstRead.src or (dst is None), (srcWrite, dstRead)
        hasValid = self._rtlUseValid
        hasReady = self._rtlUseReady

        if regCnt == 0:
            # assert (not srcWrite._rtlUseValid and not srcWrite._rtlUseReady) or dstRead not in allocator.subNodes, (
            #    dstRead, "Channels to same cycle in same ArchElement would create a combinational loops in sync")
            assert self._fullPort is None, self
            if dst is None and dstRead.src is None:
                assert HdlType_isVoid(dstRead._portDataOut._dtype), (srcWrite, dstRead)
            else:
                dstRead.src(dst)
            vld = None
        else:
            assert regCnt >= 0, self
            parentHwModule = allocator.netlist.parentHwModule

            for hwIO in dstRead.src._hwIOs:
                hwIO._sig._isUnnamedExpr = False

            channelInitValues = self.associatedRead.channelInitValues
            if hasValid and hasReady:
                name = self.buffName if self.buffName else f"{allocator.namePrefix:s}n{self._id:d}"

                buffs = HsBuilder(parentHwModule, dst, name)\
                    .buff(regCnt, init_data=channelInitValues).end

                dstRead.src(buffs)

                for hwIO in buffs._hwIOs:
                    hwIO._sig._isUnnamedExpr = False
                vld = buffs.vld
            else:
                if regCnt > 2:
                    raise NotImplementedError("Prefer use of FIFO")
                hasData = not HdlType_isVoid(dstRead._portDataOut._dtype)
                if hasData:
                    if hasReady or hasValid:
                        data = dst.data
                    else:
                        data = dst

                namePrefix = f"{allocator.namePrefix:s}n{self._id:d}_"
                vld = None
                if hasValid:
                    assert dstRead.src is not dst, dstRead
                    vld = dst.vld
                    assert len(channelInitValues) <= regCnt, self
                    for i, initVal in zip_longest(range(regCnt), channelInitValues, fillvalue=NOT_SPECIFIED):
                        if hasData:
                            if initVal is NOT_SPECIFIED:
                                initVal = None
                            else:
                                assert len(initVal) == 1, initVal
                                initVal = initVal[0]
                            data = parentHwModule._reg(f"{namePrefix:s}{i:d}_data", data._dtype,
                                                       nextSig=data, def_val=initVal)

                        # vld, full = dstRead.rtlAllocChannelDataVldAndFullReg(allocator)
                        vld = parentHwModule._reg(f"{namePrefix:s}{i:d}_vld", nextSig=vld,
                                                  def_val=int(initVal is not NOT_SPECIFIED))
                    if hasData:
                        dstRead.src.data(data)
                    dstRead.src.vld(vld)
                elif hasReady:
                    raise NotImplementedError(self)
                elif hasData:
                    assert dstRead.src is not dst, dstRead
                    for i, initVal in zip_longest(range(regCnt), channelInitValues, fillvalue=NOT_SPECIFIED):
                        if initVal is NOT_SPECIFIED:
                            initVal = None
                        else:
                            assert len(initVal) == 1, initVal
                            initVal = initVal[0]
                        data = parentHwModule._reg(f"{namePrefix:s}{i:d}_data", data._dtype,
                                                   nextSig=data, def_val=initVal)
                    dstRead.src(data)

        # self._rtlAllocRegisterReadySignal(allocator, lambda: dst.rd)
        self._rtlAllocRegisterFullSignal(allocator, vld)

        return res

    def _rtlAllocAsRegOrImmediate(self, allocator: "ArchElement", dstRead: HlsNetNodeRead):
        srcWrite = self
        clkPeriod = allocator.netlist.normalizedClkPeriod
        wTime = srcWrite.scheduledIn[0]
        rTime = dstRead.scheduledOut[0]
        wClkI = clkWindowIndex(wTime, clkPeriod)
        rClkI = clkWindowIndex(rTime, clkPeriod)
        assert dstRead in allocator.subNodes, (
            self, allocator, "If this backedge is not buffer both write and read must be in same element")

        hasOnlyVoidData = HdlType_isVoid(self.dependsOn[0]._dtype)
        # :var dataDst: the signal which holds the value which is an output of an associated read
        # :var dataSrc: the signal which holds the value which is an input to this write
        if hasOnlyVoidData:
            dataDst = dataSrc = None
        else:
            rData: TimeIndependentRtlResource = allocator.rtlAllocHlsNetNodeOut(self.associatedRead._portDataOut)
            src = allocator.rtlAllocHlsNetNodeOut(self.dependsOn[0])
            if HdlType_isVoid(self.dependsOn[0]._dtype):
                dataSrc = 1
            else:
                dataSrc = src.get(wTime).data

            dataDst = rData.get(rTime).data

        # the value is not cleared properly on read if it is not written
        vldDst, fullReg = dstRead.rtlAllocChannelDataVldAndFullReg(allocator)
        wEn = allocator.rtlAllocHlsNetNodeInDriverIfExists(self.extraCond)
        if wEn is not None:
            wEn = wEn.data
            # if isinstance(wEn, HConst):
            #    raise AssertionError("The enable condition for a channel should never be constant,"
            #                         " if 1 the condition should be removed, if 0 the channel should be removed", wEn, self)

        isReg = self.allocationType == CHANNEL_ALLOCATION_TYPE.REG
        rwMayHappenAtOnce = rClkI == wClkI or allocator.rtlStatesMayHappenConcurrently(rClkI, wClkI)
        wStageCon: "ConnectionsOfStage" = allocator.connections[wClkI]

        if wEn is None:
            # write is always active
            res = []
            if vldDst is not None:
                res.append(vldDst(1))
            if fullReg is not None:
                assert isReg, self
                res.append(fullReg(1))
            if dataDst is not None:
                res.append(dataDst(dataSrc))
        else:
            if isReg:
                if rwMayHappenAtOnce:
                    assert dstRead in allocator.subNodes, ("If this is REG this the other side of port must be in the same ArchElement")
                    rEn = allocator.rtlAllocHlsNetNodeInDriverIfExists(dstRead.extraCond)
                    if rEn is not None:
                        rEn = rEn.data
                else:
                    rEn = None

                assert vldDst is not None or dataDst is not None or fullReg is not None, self
                # :attention: HlsArchPassSyncLowering may replace original valid/validNB.
                #   If read was blocking the parent syncNode is stalling while not full.
                #   if read was non-blocking the valid/validNB is replaced with validNB & full
                #   this expression is captured in register directly after clock window with read.
                if fullReg is None:
                    regToSignalizeFull = vldDst
                else:
                    regToSignalizeFull = fullReg
                if isinstance(wEn, HConst):
                    if wEn:
                        res = [
                            fullReg(1) if fullReg is not None else (),
                            vldDst(1) if vldDst is not None else (),
                            dataDst(dataSrc) if dataDst is not None else (),
                        ]
                    else:
                        if regToSignalizeFull is not None and rwMayHappenAtOnce:
                            # clear fullReg if read is performed
                            if rEn is None:
                                # read is always performed
                                res = [regToSignalizeFull(0), ]
                            else:
                                assert not isinstance(rEn, HConst), rEn
                                res = [
                                    If(rEn,
                                        regToSignalizeFull(0),
                                    ),
                                ]
                        else:
                            res = []
                else:
                    res = If(wEn,
                             fullReg(1) if fullReg is not None else (),
                             vldDst(1) if vldDst is not None else (),
                             dataDst(dataSrc) if dataDst is not None else (),
                          )
                    if regToSignalizeFull is not None and rwMayHappenAtOnce:
                        # clear fullReg if read is performed
                        if rEn is None:
                            # read is always performed
                            res = res.Else(
                                    regToSignalizeFull(0),
                                  )
                        else:
                            res = res.Elif(rEn,
                                    regToSignalizeFull(0),
                                  )
                    res = [res, ]
            else:
                assert self.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE, self.allocationType
                if dataDst is None:
                    res = []
                else:
                    assert dataDst._dtype == BIT, ("This was only intended for control", dataDst, dataDst._dtype)
                    res = [dataDst(dataSrc & wEn)]

                if vldDst is not None:
                    assert vldDst._nop_val is NOT_SPECIFIED, (vldDst, vldDst._nop_val)
                    vldDst._nop_val = vldDst._dtype.from_py(0)
                    _res = vldDst(wEn)
                    # wStageCon.stateChangeDependentDrives.append(_res)
                    res.append(_res)

        self._rtlAllocRegisterReadySignal(allocator, lambda:~vldDst | rEn if rwMayHappenAtOnce else ~vldDst)
        self._rtlAllocRegisterFullSignal(allocator, vldDst if fullReg is None else fullReg)

        # vldDst is not provided to rtlAllocDatapathWrite because it has custom driver in res
        allocator.rtlAllocDatapathWrite(self, None, wStageCon, res)
        return res

    @override
    def rtlAllocAsIO(self, allocator: "ArchElement") -> list[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert len(self.dependsOn) >= 1, (self, self.dependsOn)

        # apply indexes before assignments
        dep = self.dependsOn[0]
        assert dep is not None, self

        if self.hasValid() or self.hasValidNB():
            raise AssertionError("Valid of write is always 1 and this port should be already optimized out")

        if self.hasAnyUsedReadyPort():
            self._rtlAllocReadyPorts(allocator)

        _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, self.scheduledIn[0])

        dst = self.dst
        if not self.rtlPortPhysicallyExits():
            assert self.isChannel(), self
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
        clkI = clkWindowIndex(self.scheduledIn[0], allocator.netlist.normalizedClkPeriod)
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

        return rtlObj

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        :note: If allocationType is CHANNEL_ALLOCATION_TYPE.REG the registers are always allocated in the time
            of read. If read and write may happen in different times
            the creates a logic which will reset the validity bit of this reg.
        """
        assert not self._isRtlAllocated, self
        assert self.skipWhen is None, ("skipWhen should have been lowered during HlsArchPassSyncLowering", self)
        assert self._forceEnPort is None, ("forceEnPort should have been lowered during HlsArchPassSyncLowering", self)

        dstRead = self.associatedRead
        if dstRead is None:
            res = self.rtlAllocAsIO(allocator)
        else:
            dstRead._rtlAllocDatapathIo()

            if self.allocationType == CHANNEL_ALLOCATION_TYPE.BUFFER:
                res = self._rtlAllocAsBuffer(allocator, dstRead)
            else:
                res = self._rtlAllocAsRegOrImmediate(allocator, dstRead)

            allocator.netNodeToRtl[self] = res
        self._isRtlAllocated = True
        return res

    def _getInterfaceName(self, io: Union[HwIO, list[HwIO]]) -> str:
        return HlsNetNodeRead._getInterfaceName(self, io)

    def __repr__(self, minify=False):
        src = self.dependsOn[0]
        allocationType = self.allocationType
        if allocationType != CHANNEL_ALLOCATION_TYPE.BUFFER:
            allocationType = " " + allocationType.name
        else:
            allocationType = ""
        if self.isChannel():
            if self.isBackedge():
                allocationType += " backedge"
            else:
                allocationType += " forwardedge"

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
            yield self.associatedRead, self.isBackedge()
