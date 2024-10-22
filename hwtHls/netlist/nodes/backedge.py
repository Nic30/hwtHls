from itertools import zip_longest
from typing import Optional, Generator, Union, Tuple, Callable

from hwt.code import If
from hwt.code_utils import rename_signal
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import OutputMinUseTimeGetter
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtLib.handshaked.builder import HsBuilder


class HlsNetNodeReadBackedge(HlsNetNodeRead):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    
    :ivar _rtlDataVldReg: a rtl signal or register holding data and validity signal
    :ivar _rtlFullReg: for allocationType == CHANNEL_ALLOCATION_TYPE.REG with full port this holds a register
        which is 1 if data was written (or there is init value) and not yet read
    """

    def __init__(self, netlist:"HlsNetlistCtx", dtype: HdlType, name: Optional[str]=None, channelInitValues=()):
        HlsNetNodeRead.__init__(self, netlist, None, dtype=dtype, name=name, channelInitValues=channelInitValues)
        self._rtlDataVldReg:Optional[Union[RtlSyncSignal, HwIO]] = None
        self._rtlFullReg:Optional[Union[RtlSyncSignal, HwIO]] = None

    @override
    def getSchedulingResourceType(self):
        return self

    @override
    def scheduleAlapCompaction(self,
                               endOfLastClk:int,
                               outputMinUseTimeGetter:Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]):
        if not self._inputs and not any(self.usedBy):
            # use time from backedge because this node is not connected to anything and floating freely in time
            raise AssertionError("The node must have at least ordering connection to write, it can not just freely float in time", self)
        return HlsNetNodeRead.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter, excludeNode)

    def rtlAllocDataVldAndFullReg(self, allocator:"ArchElement") -> Tuple[Optional[Union[RtlSyncSignal, HwIO]], Optional[Union[RtlSyncSignal, HwIO]]]:
        # check if this was already allocated to support re-entrability
        if self._rtlDataVldReg is not None or self._rtlFullReg is not None:
            return self._rtlDataVldReg, self._rtlFullReg

        # for vldOut in (self._valid, self._validNB):
        #    if vldOut is None:
        #        continue
        #    cur = allocator.netNodeToRtl.get(vldOut)
        #    assert cur is None, (vldOut, "port should not be allocated because _rtlDataVldReg was not set yet")
        hasVld = self.hasAnyFormOfValidPort()
        hasFull = self.associatedWrite is not None and self.associatedWrite._fullPort is not None
        dataVldReg: Optional[Union[RtlSyncSignal, HwIO]] = None
        fullReg: Optional[Union[RtlSyncSignal, HwIO]] = None
        srcWrite: HlsNetNodeWriteBackedge = self.associatedWrite
        dataRegName = f"{allocator.namePrefix:s}{self.name:s}"
        capacity = srcWrite._getBufferCapacity()
        if srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.REG and capacity == 1:
            hadInit = bool(self.channelInitValues)
            if hasVld:
                dataVldReg = allocator._reg(f"{dataRegName:s}_vld", BIT, def_val=int(hadInit))
                dataVldReg.hidden = False
            if hasFull:
                fullReg = allocator._reg(f"{dataRegName:s}_full", BIT, def_val=int(hadInit))
                fullReg.hidden = False
        elif srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE or capacity == 0:
            dataVldReg = allocator._sig(f"{dataRegName:s}_vld", BIT)
            assert not hasFull, self
        else:
            raise NotImplementedError(self)

        for vldOut in (self._valid, self._validNB):
            if vldOut is None:
                continue
            allocator.rtlRegisterOutputRtlSignal(vldOut, dataVldReg, False, False, True)

        self._rtlDataVldReg = dataVldReg
        self._rtlFullReg = fullReg

        return dataVldReg, fullReg

    def _mayHappenConcurrentlyWithWrite(self):
        w = self.associatedWrite
        assert w is not None, self
        rParent, rClkI = self.getParentSyncNode()
        rParent: "ArchElement"
        wParent, wClkI = w.getParentSyncNode()
        if rParent is wParent:
            return rClkI == wClkI or rParent.rtlStatesMayHappenConcurrently(rClkI, wClkI)
        else:
            return True

    @override
    def rtlAlloc(self, allocator:"ArchElement") -> TimeIndependentRtlResource:
        """
        :note: For doc see :meth:`HlsNetNodeWriteBackedge.rtlAlloc`
        """
        assert not self._isRtlAllocated, self
        assert self._rawValue is None, ("access to a _rawValue should be already lowered and this port should be removed", self)
        dataOut = self._portDataOut
        hasNoSpecialControl = self._isBlocking and not self.hasValidNB() and not self.hasValid()
        self._rtlAllocDatapathIo()

        srcWrite: HlsNetNodeWriteBackedge = self.associatedWrite
        if srcWrite is None or srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.BUFFER:
            # allocate as a read from buffer output interface
            return HlsNetNodeRead.rtlAlloc(self, allocator)
        else:
            assert not self._isRtlAllocated, self
            # allocate as a register
            if self._dataVoidOut is not None:
                HlsNetNodeRead._rtlAllocDataVoidOut(self, allocator)

            init = self.channelInitValues
            assert self.name is not None, self
            dataRegName = f"{allocator.namePrefix:s}{self.name:s}"
            dtype = dataOut._dtype
            if not HdlType_isVoid(dtype):
                dtype = self.getRtlDataSig()._dtype
            if srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.REG and srcWrite._getBufferCapacity() > 0:
                if init:
                    if len(init) > 1:
                        raise NotImplementedError(self, init)
                else:
                    init = ((0,),)

                if HdlType_isVoid(dtype):
                    # assert not self.usedBy[0], self
                    dataReg = []
                else:
                    _init = init[0][0]
                    dataReg = allocator._reg(dataRegName, dtype, def_val=_init)
                    dataReg.hidden = False
            else:
                assert srcWrite.allocationType in (CHANNEL_ALLOCATION_TYPE.IMMEDIATE,
                                                   CHANNEL_ALLOCATION_TYPE.REG), srcWrite.allocationType
                assert not init, ("Immediate channels can not have init value", srcWrite, init)
                dataReg = allocator._sig(dataRegName, dtype)

            dataVldReg, fullReg = self.rtlAllocDataVldAndFullReg(allocator)

            dstRead = self
            clkPeriod = self.netlist.normalizedClkPeriod
            rClkI = indexOfClkPeriod(dstRead.scheduledOut[0], clkPeriod)
            rStageCon = allocator.connections[rClkI]
            res = []
            if fullReg is not None or dataVldReg is not None:
                if srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
                    rwMayHappenAtOnce = self._mayHappenConcurrentlyWithWrite()
                    if rwMayHappenAtOnce:
                        # if this may happen concurrently this is handled in rtlAlloc of write
                        pass
                    else:
                        # resolve "ready"
                        if fullReg is not None:
                            res = [fullReg(0), ]
                        else:
                            res = [dataVldReg(0), ]
                        #en = allocator._rtlAllocDatapathGetIoAck(self, allocator.namePrefix)
                        en = allocator.rtlAllocHlsNetNodeInDriverIfExists(self.extraCond)
                        if en is not None:
                            res = [If(en.data, res), ]
                        # rStageCon.stateChangeDependentDrives.append(res)
                
            if  dataVldReg is not None:
                if self._rtlUseValid:
                    assert not self.src.vld._sig.drivers, (self, self.src.vld._sig.drivers)
                    self.src.vld(dataVldReg)

            # create RTL signal expression base on operator type
            if HdlType_isVoid(dtype):
                # assert not self.usedBy[0], self
                dataRegTir = allocator.netNodeToRtl[dataOut] = []
            else:
                isReg = srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.REG
                dataRegTir = allocator.rtlRegisterOutputRtlSignal(dataOut, dataReg, isReg, False, True)

            allocator.rtlAllocDatapathRead(self, None, rStageCon, res)  # , validHasCustomDriver=True, readyHasCustomDriver=True
            self._isRtlAllocated = True
            return dataRegTir if hasNoSpecialControl else []


class HlsNetNodeWriteBackedge(HlsNetNodeWrite):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.

    :ivar buffName: name which can be used to override the name of the buffer in RTL
    """
    _PORT_ATTR_NAMES = HlsNetNodeWrite._PORT_ATTR_NAMES + ["_fullPort"]

    def __init__(self, netlist:"HlsNetlistCtx",
                 name:Optional[str]=None,
                 mayBecomeFlushable:bool=False):
        HlsNetNodeWrite.__init__(self, netlist, None, name=name, mayBecomeFlushable=mayBecomeFlushable)
        self._loopChannelGroup: Optional["LoopChanelGroup"] = None

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNodeWriteBackedge", bool]:
        y, isNew = HlsNetNodeRead.clone(self, memo, keepTopPortsConnected)
        if isNew:
            lcg = self._loopChannelGroup
            if lcg is not None:
                y._loopChannelGroup = lcg.clone
        return y, isNew

    @override
    def isForwardedge(self):
        return False

    @override
    def isBackedge(self):
        return True

    @override
    def _removeOutput(self, index:int):
        if self._fullPort is not None and self._fullPort.out_i == index:
            self._fullPort = None
        return HlsNetNodeWrite._removeOutput(self, index)

    @override
    def getSchedulingResourceType(self):
        return self

    @override
    def _getBufferCapacity(self):
        # srcWrite = self
        dstRead = self.associatedRead
        if dstRead is None or self.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE:
            return 0
        assert dstRead is not None
        # dst_t = dstRead.scheduledOut[0]
        # src_t = srcWrite.scheduledIn[0]
        # assert dst_t < src_t, (self, dst_t, src_t)
        return 1

    def _rtlAllocRegisterReadySignal(self, allocator: "ArchElement", readySignalGetter: Callable[[], RtlSyncSignal]):
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

    def _rtlAllocRegisterFullSignal(self, allocator: "ArchElement", full: RtlSyncSignal):
        if self._fullPort is not None:
            assert full is not None, ("If node has full port it should also have a valid port", self)
            if allocator._dbgAddSignalNamesToSync:
                full = rename_signal(allocator, full, f"{self.name:s}_full")
            allocator.rtlRegisterOutputRtlSignal(self._fullPort, full, True, False, True)

    def _rtlAllocAsBuffer(self, allocator: "ArchElement", dstRead: HlsNetNodeReadBackedge):
        """
        :note: if the write is flushable the srcWrite.dst sync signals drivers are altered
            and the code of this function does not care about it
        """
        srcWrite = self
        dst = srcWrite.dst
        res = HlsNetNodeWrite.rtlAlloc(self, allocator)
        assert dstRead is not None
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
                hwIO._sig.hidden = False
            
            channelInitValues = self.associatedRead.channelInitValues
            if hasValid and hasReady:
                name = self.buffName if self.buffName else f"{allocator.namePrefix:s}n{self._id:d}"

                buffs = HsBuilder(parentHwModule, dst, name)\
                    .buff(regCnt, init_data=channelInitValues).end

                dstRead.src(buffs)

                for hwIO in buffs._hwIOs:
                    hwIO._sig.hidden = False
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

                        # vld, full = dstRead.rtlAllocDataVldAndFullReg(allocator)
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

    def _rtlAllocAsRegOrImmediate(self, allocator: "ArchElement", dstRead: HlsNetNodeReadBackedge):
        srcWrite = self
        clkPeriod = allocator.netlist.normalizedClkPeriod
        wTime = srcWrite.scheduledIn[0]
        rTime = dstRead.scheduledOut[0]
        wClkI = indexOfClkPeriod(wTime, clkPeriod)
        rClkI = indexOfClkPeriod(rTime, clkPeriod)
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
        vldDst, fullReg = dstRead.rtlAllocDataVldAndFullReg(allocator)
        wEn = allocator.rtlAllocHlsNetNodeInDriverIfExists(self.extraCond)
        # wEn = allocator._rtlAllocDatapathGetIoAck(self, allocator.namePrefix)
        #forceEn = allocator.rtlAllocHlsNetNodeInDriverIfExists(self._forceEnPort)
        if wEn is not None:
            wEn = wEn.data
        #if wEn is None:
        #    if forceEn is not None:
        #        wEn = forceEn.data
        #elif forceEn is not None:
        #    wEn = wEn.data | forceEn.data
        #else:
        #    wEn = wEn.data

        isReg = self.allocationType == CHANNEL_ALLOCATION_TYPE.REG
        rwMayHappenAtOnce = rClkI == wClkI or allocator.rtlStatesMayHappenConcurrently(rClkI, wClkI)
        wStageCon: ConnectionsOfStage = allocator.connections[wClkI]

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
            # if isRegWithCapacity:
            #    wStageCon.stateChangeDependentDrives.extend(res)
        else:
            if isReg:
                if rwMayHappenAtOnce:
                    assert dstRead in allocator.subNodes, ("If this is REG this the other side of port must be in the same ArchElement")
                    rEn = allocator.rtlAllocHlsNetNodeInDriverIfExists(dstRead.extraCond)
                    if rEn is not None:
                        rEn = rEn.data
                    #rEn = allocator._rtlAllocDatapathGetIoAck(dstRead, allocator.namePrefix)
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
                # if isRegWithCapacity:
                #    wStageCon.stateChangeDependentDrives.extend(res)
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
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        :note: If allocationType is CHANNEL_ALLOCATION_TYPE.REG the registers are always allocated in the time
            of read. If read and write may happen in different times
            the creates a logic which will reset the validity bit of this reg.
        """
        assert not self._isRtlAllocated, self
        assert self.skipWhen is None, ("skipWhen should have been lowered during HlsArchPassSyncLowering", self)
        assert self._forceEnPort is None, ("forceEnPort should have been lowered during HlsArchPassSyncLowering", self)

        dstRead: HlsNetNodeReadBackedge = self.associatedRead
        dstRead._rtlAllocDatapathIo()

        # isForwardEdge = wTime < rTime
        if self.allocationType == CHANNEL_ALLOCATION_TYPE.BUFFER:
            res = self._rtlAllocAsBuffer(allocator, dstRead)
        else:
            res = self._rtlAllocAsRegOrImmediate(allocator, dstRead)

        allocator.netNodeToRtl[self] = res
        self._isRtlAllocated = True
        return res

    @override
    def debugIterShadowConnectionDst(self) -> Generator[Tuple[HlsNetNode, bool], None, None]:
        if self.associatedRead is not None:
            yield self.associatedRead, True

