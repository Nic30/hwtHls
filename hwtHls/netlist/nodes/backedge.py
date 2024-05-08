from enum import Enum
from itertools import zip_longest
from typing import Optional, Generator, Union, Tuple

from hwt.code import If
from hwt.code_utils import rename_signal
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.rdSyncedStructIntf import RdSyncedStructIntf
from hwt.interfaces.std import HandshakeSync, VldSync, RdSync
from hwt.interfaces.structIntf import HdlType_to_Interface
from hwt.interfaces.vldSyncedStructIntf import VldSyncedStructIntf
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwt.synthesizer.unit import Unit
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import OutputMinUseTimeGetter
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.typingFuture import override
from hwtLib.handshaked.builder import HsBuilder


class HlsNetNodeReadBackedge(HlsNetNodeRead):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.
    """

    def __init__(self, netlist:"HlsNetlistCtx", dtype: HdlType, name: Optional[str]=None):
        HlsNetNodeRead.__init__(self, netlist, None, dtype=dtype, name=name)
        self.associatedWrite: Optional[HlsNetNodeWriteBackedge] = None
        self._rtlIoAllocated = False
        self._rtlDataVldReg:Optional[Union[RtlSyncSignal, Interface]] = None

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool):
        y, isNew = HlsNetNodeRead.clone(self, memo, keepTopPortsConnected)
        if isNew:
            if self.associatedWrite is not None:
                y.associatedWrite = self.associatedWrite.clone(memo, True)
        return y, isNew

    def getAssociatedWrite(self):
        return self.associatedWrite

    @override
    def getSchedulingResourceType(self):
        return self

    @override
    def scheduleAlapCompaction(self, endOfLastClk:int, outputMinUseTimeGetter:Optional[OutputMinUseTimeGetter]):
        if not self._inputs and not any(self.usedBy):
            # use time from backedge because this node is not connected to anything and floating freely in time
            raise AssertionError("The node must have at least ordering connection to write, it can not just freely float in time", self)
        return HlsNetNodeRead.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter)

    @override
    def hasValidOnlyToPassFlags(self):
        if self._rtlUseValid:
            return False

        w = self.associatedWrite
        if w is None:
            return False

        if w.extraCond is not None and HlsNetNodeExplicitSync.hasValidOnlyToPassFlags(self):
            return True

        if w._loopChannelGroup is not None and w._loopChannelGroup.getChannelWhichIsUsedToImplementControl() == w:
            return True  # because we need valid for loop to know that the channel is active

        return False

    @override
    def hasReadyOnlyToPassFlags(self):
        if self._rtlUseReady or isinstance(self, HlsNetNodeReadBackedge):
            # backedges do not require ready=read.extraCond
            # because if ready was removed it means that ready is always 1
            # it the write is going to be performed
            return False

        w = self.associatedWrite
        if w is None:
            return False

        if self.extraCond is not None and HlsNetNodeExplicitSync.hasReadyOnlyToPassFlags(w):
            # read extra cond may cause stall, and w is checking ready
            return True

        return False

    def _rtlAllocDatapathIo(self):
        """
        Load declaration of the interface and construct its RTL signals.
        """
        if not self._rtlIoAllocated:
            hasValid = self._rtlUseValid or self.hasValidOnlyToPassFlags()
            hasReady = self._rtlUseReady or self.hasReadyOnlyToPassFlags()
            # if (isinstance(self, HlsNetNodeRead) and self.associatedWrite._getBufferCapacity() == 0) or \
            #        (isinstance(self, HlsNetNodeWrite) and self._getBufferCapacity() == 0):
            #        hasValid &= self._rtlUseReady
            #        hasReady &= self._rtlUseValid

            u:Unit = self.netlist.parentUnit
            assert self.src is None, (
                "Src interface must not be yet instantiated on parent Unit", self, self.src)
            w = self.associatedWrite
            assert w.dst is None, (w, w.dst)
            dtype = self._outputs[0]._dtype
            if HdlType_isVoid(dtype):
                if hasValid and hasReady:
                    src = HandshakeSync()
                elif hasValid:
                    src = VldSync()
                elif hasReady:
                    src = RdSync()
                else:
                    src = None

            else:
                if hasValid and hasReady:
                    src = HsStructIntf()
                    src.T = dtype
                elif hasValid:
                    src = VldSyncedStructIntf()
                    src.T = dtype
                elif hasReady:
                    src = RdSyncedStructIntf()
                    src.T = dtype
                else:
                    src = HdlType_to_Interface().apply(dtype)

            if src is not None:
                src._name = self.name

                self.src = Interface_without_registration(u, src, src._name)
            # :note: getattr used to avoid cyclic dependencies in HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge classes
            allocTy = getattr(w, "allocationType", None)
            if allocTy == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE:
                w.dst = self.src
            else:
                if src is None:
                    w.dst = None
                else:
                    w.dst = Interface_without_registration(u, self.src.__copy__(), f"{self.netlist.namePrefix}{w.name:s}")

            self._rtlIoAllocated = True

    def rtlAllocDataVldReg(self, allocator:"ArchElement") -> RtlSignalBase:
        assert self.hasAnyFormOfValidPort(), self

        # check if this was already allocated to support re-entrability
        if self._rtlDataVldReg is not None:
            return self._rtlDataVldReg

        for vldOut in (self._valid, self._validNB):
            if vldOut is None:
                continue
            cur = allocator.netNodeToRtl.get(vldOut)
            assert cur is None, (vldOut, "port should not be allocated because _rtlDataVldReg was not set yet")

        srcWrite: HlsNetNodeWriteBackedge = self.associatedWrite
        dataRegName = f"{allocator.name:s}{self.name:s}"
        capacity = srcWrite._getBufferCapacity()
        if srcWrite.allocationType == BACKEDGE_ALLOCATION_TYPE.REG and capacity > 0:
            hadInit = bool(srcWrite.channelInitValues)
            dataVldReg = allocator._reg(f"{dataRegName:s}_vld", BIT, def_val=int(hadInit))
            dataVldReg.hidden = False
        elif srcWrite.allocationType == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE or capacity == 0:
            dataVldReg = allocator._sig(f"{dataRegName:s}_vld", BIT)
        else:
            raise NotImplementedError(self)

        for vldOut in (self._valid, self._validNB):
            if vldOut is None:
                continue
            allocator.rtlRegisterOutputRtlSignal(vldOut, dataVldReg, False, False, True)

        self._rtlDataVldReg = dataVldReg

        return dataVldReg

    @override
    def rtlAlloc(self, allocator:"ArchElement") -> TimeIndependentRtlResource:
        """
        :note: For doc see :meth:`HlsNetNodeWriteBackedge.rtlAlloc`
        """
        assert not self._isRtlAllocated, self
        assert self._rawValue is None, ("access to a _rawValue should be already lowered and this port should be removed", self)
        dataOut = self._outputs[0]
        hasNoSpecialControl = self._isBlocking and not self.hasValidNB() and not self.hasValid()
        self._rtlAllocDatapathIo()

        srcWrite: HlsNetNodeWriteBackedge = self.associatedWrite
        if srcWrite is None or srcWrite.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
            # allocate as a read from buffer output interface
            return HlsNetNodeRead.rtlAlloc(self, allocator)
        else:
            assert not self._isRtlAllocated, self
            # allocate as a register
            if self._dataVoidOut is not None:
                HlsNetNodeRead._rtlAllocDataVoidOut(self, allocator)

            init = self.associatedWrite.channelInitValues
            assert self.name is not None, self
            dataRegName = f"{allocator.name:s}{self.name:s}"
            dtype = dataOut._dtype
            if not HdlType_isVoid(dtype):
                dtype = self.getRtlDataSig()._dtype
            requiresVld = self.hasAnyFormOfValidPort()
            if srcWrite.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
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
                assert srcWrite.allocationType == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE, srcWrite.allocationType
                assert not init, ("Immediate channels can not have init value", srcWrite, init)
                dataReg = allocator._sig(dataRegName, dtype)

            if requiresVld:
                dataVldReg = self.rtlAllocDataVldReg(allocator)

            dstRead = self
            clkPeriod = self.netlist.normalizedClkPeriod
            rTime = dstRead.scheduledOut[0]
            rClkI = indexOfClkPeriod(rTime, clkPeriod)
            rStageCon = allocator.connections[rClkI]
            if requiresVld:
                if srcWrite.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
                    wTime = srcWrite.scheduledIn[0]
                    wClkI = indexOfClkPeriod(wTime, clkPeriod)
                    rwMayHappenAtOnce = rClkI == wClkI or allocator.rtlStatesMayHappenConcurrently(rClkI, wClkI)

                    if rwMayHappenAtOnce:
                        # if this may happen concurrently this is handled in rtlAlloc of write
                        pass
                    else:
                        # resolve "ready"
                        res = dataVldReg(0)
                        en = HlsNetNodeWriteBackedge._getRtlEnableForNonBufferReg(self, allocator)
                        if en is not None:
                            res = If(en, res)
                        rStageCon.stDependentDrives.append(res)

                if self._rtlUseValid and not self.hasValidOnlyToPassFlags():
                    assert not self.src.vld._sig.drivers, (self, self.src.vld._sig.drivers)
                    self.src.vld(dataVldReg)

            # create RTL signal expression base on operator type
            if HdlType_isVoid(dtype):
                # assert not self.usedBy[0], self
                dataRegTir = allocator.netNodeToRtl[dataOut] = []
            else:
                isReg = srcWrite.allocationType == BACKEDGE_ALLOCATION_TYPE.REG
                dataRegTir = allocator.rtlRegisterOutputRtlSignal(dataOut, dataReg, isReg, False, True)

            allocator.rtlAllocDatapathRead(self, rStageCon, [], validHasCustomDriver=True, readyHasCustomDriver=True)
            self._isRtlAllocated = True
            return dataRegTir if hasNoSpecialControl else []


class BACKEDGE_ALLOCATION_TYPE(Enum):
    """
    :cvar IMMEDIATE: The signal will be used as is without any buffer. This also means that the value of data is not stable and must be immediately used.
        An extra care must be taken to prove that this kind of buffer does not create a combinational loop.
    :cvar REG: Allocate as a DFF register. Used if it is proven that the size of buffer will be max 1 to spare HW resources and to simplify synchronization logic.
    :cvar BUFFER: Object allocates a buffer of length specified by time difference between read/write.
    """
    IMMEDIATE, REG, BUFFER = range(3)


class HlsNetNodeWriteBackedge(HlsNetNodeWrite):
    """
    The read from HLS pipeline which is binded to a buffer for data/sync on backward edge in dataflow graph.

    :ivar channelInitValues: Optional tuple for value initialization.
    :ivar buffName: name which can be used to override the name of the buffer in RTL
    :ivar _fullPort: :see: :meth:`~.HlsNetNodeWriteBackedge.getFullPort` 
    """

    def __init__(self, netlist:"HlsNetlistCtx",
                 channelInitValues=(),
                 name:Optional[str]=None):
        HlsNetNodeWrite.__init__(self, netlist, None, name=name)
        self.associatedRead: Optional[HlsNetNodeReadBackedge] = None
        self.channelInitValues = channelInitValues
        self.allocationType = BACKEDGE_ALLOCATION_TYPE.BUFFER
        self.buffName = None
        self._loopChannelGroup: Optional["LoopChanelGroup"] = None
        self._fullPort: Optional[HlsNetNodeOut] = None

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNodeWriteBackedge", bool]:
        y, isNew = HlsNetNodeRead.clone(self, memo, keepTopPortsConnected)
        if isNew:
            read = self.associatedRea
            if read is not None:
                y.associatedRead = read.clone(memo)
            fullPort = self._fullPort
            if fullPort is not None:
                y._fullPort = y._outputs[fullPort.out_i]
            lcg = self._loopChannelGroup
            if lcg is not None:
                y._loopChannelGroup = lcg.clone
        return y, isNew

    def associateRead(self, read: HlsNetNodeReadBackedge):
        assert isinstance(read, HlsNetNodeReadBackedge), ("Can associate only with read of compatible type", read, self)
        read.associatedWrite = self
        self.associatedRead = read

    def getAssociatedWrite(self):
        return self

    def getFullPort(self) -> HlsNetNodeOut:
        """
        :attention: This port should be used only after scheduling to access internal state of the buffer.
            Under normal scenario one should use ready/readyNB.
        :return: port which is 1 if there is a space in the buffer of this edge.
        """
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

    @override
    def _removeOutput(self, index:int):
        if self._fullPort is not None and self._fullPort.out_i == index:
            self._fullPort = None
        return HlsNetNodeWrite._removeOutput(self, index)

    @override
    def hasValidOnlyToPassFlags(self):
        return self.associatedRead.hasValidOnlyToPassFlags()

    @override
    def hasReadyOnlyToPassFlags(self):
        return self.associatedRead.hasReadyOnlyToPassFlags()

    @override
    def getSchedulingResourceType(self):
        return self

    def _getRtlEnableForNonBufferReg(self, allocator: "ArchElement"):
        """
        If this read-write pair is not instantiated as a buffer it means it does not have associated IO interface.
        In this specific case we have to explicitly resolve synchronization.
        A reg is written to if it is enabled and not skipped and if every other IO in this clock is either enabled and
        receives ack from outside or it is skipped.
        """
        # :note: _rtlAllocDatapathAddIoToConnections args are None because this node is only one who is using the channel port
        en = allocator._rtlAllocDatapathGetIoAck(self, allocator.name)
        return en

    def _getBufferCapacity(self):
        srcWrite = self
        dstRead = self.associatedRead
        assert dstRead is not None
        dst_t = dstRead.scheduledOut[0]
        src_t = srcWrite.scheduledIn[0]
        assert dst_t <= src_t, (self, dst_t, src_t)
        if self.allocationType == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE:
            return 0
        else:
            return 1

    def rtlAllocAsBuffer(self, allocator: "ArchElement", dstRead: HlsNetNodeReadBackedge):
        srcWrite = self
        res = HlsNetNodeWrite.rtlAlloc(self, allocator)
        assert dstRead is not None
        regCnt = self._getBufferCapacity()
        assert srcWrite.dst is not dstRead.src or (srcWrite.dst is None), (srcWrite, dstRead)
        if regCnt == 0:
            assert not srcWrite._rtlUseValid and srcWrite._rtlUseReady or dstRead not in allocator._subNodes, (
                dstRead, "Channels to same cycle in same ArchElement would create a combinational loops in sync")
            assert self._fullPort is None, self
            if srcWrite.dst is None and dstRead.src is None:
                assert HdlType_isVoid(dstRead._outputs[0]._dtype), (srcWrite, dstRead)
            else:
                dstRead.src(srcWrite.dst)
        else:
            assert regCnt >= 0, self
            hasValid = self._rtlUseValid or self.hasValidOnlyToPassFlags()
            hasReady = self._rtlUseReady or self.hasReadyOnlyToPassFlags()
            parentUnit = allocator.netlist.parentUnit
            for i in dstRead.src._interfaces:
                i._sig.hidden = False
            if hasValid and hasReady:
                buffs = HsBuilder(parentUnit, srcWrite.dst, self.buffName if self.buffName else f"{allocator.name:s}n{self._id:d}")\
                    .buff(regCnt, init_data=self.channelInitValues).end
                dstRead.src(buffs)
                for i in buffs._interfaces:
                    i._sig.hidden = False
                vld = buffs.vld
            else:
                if regCnt > 2:
                    raise NotImplementedError("Prefer use of FIFO")
                hasData = not HdlType_isVoid(dstRead._outputs[0]._dtype)
                if hasData:
                    if hasReady or hasValid:
                        data = srcWrite.dst.data
                    else:
                        data = srcWrite.dst

                namePrefix = f"{allocator.name:s}n{self._id:d}_"
                vld = None
                if hasValid:
                    assert dstRead.src is not srcWrite.dst, dstRead
                    vld = srcWrite.dst.vld
                    assert len(self.channelInitValues) <= regCnt, self
                    for i, initVal in zip_longest(range(regCnt), self.channelInitValues, fillvalue=NOT_SPECIFIED):
                        if hasData:
                            if initVal is NOT_SPECIFIED:
                                initVal = None
                            else:
                                assert len(initVal) == 1, initVal
                                initVal = initVal[0]
                            data = parentUnit._reg(f"{namePrefix:s}{i:d}_data", data._dtype, nextSig=data, def_val=initVal)

                        # vld = dstRead.rtlAllocDataVldReg(allocator)
                        vld = parentUnit._reg(f"{namePrefix:s}{i:d}_vld", nextSig=vld, def_val=int(initVal is not NOT_SPECIFIED))
                    if hasData:
                        dstRead.src.data(data)
                    dstRead.src.vld(vld)
                elif hasReady:
                    raise NotImplementedError(self)
                elif hasData:
                    assert dstRead.src is not srcWrite.dst, dstRead
                    for i, initVal in zip_longest(range(regCnt), self.channelInitValues, fillvalue=NOT_SPECIFIED):
                        if initVal is NOT_SPECIFIED:
                            initVal = None
                        else:
                            assert len(initVal) == 1, initVal
                            initVal = initVal[0]
                        data = parentUnit._reg(f"{namePrefix:s}{i:d}_data", data._dtype, nextSig=data, def_val=initVal)
                    dstRead.src(data)

            if self._fullPort is not None:
                if vld is None:
                    raise AssertionError("This channel has no form of valid but it has full which is form of valid", self)
                if allocator._dbgAddSignalNamesToSync:
                    full = rename_signal(allocator, vld, f"{self.name:s}_full")
                else:
                    full = vld
                allocator.rtlRegisterOutputRtlSignal(self._fullPort, full, True, False, True)

        return res

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        :note: If allocationType is BACKEDGE_ALLOCATION_TYPE.REG the registers are always allocated in the time
            of read. If read and write may happen in different times
            the creates a logic which will reset the validity bit of this reg.
        """
        assert not self._isRtlAllocated, self
        dstRead: HlsNetNodeReadBackedge = self.associatedRead
        dstRead._rtlAllocDatapathIo()
        srcWrite = self
        clkPeriod = allocator.netlist.normalizedClkPeriod
        wTime = srcWrite.scheduledIn[0]
        rTime = dstRead.scheduledOut[0]
        wClkI = indexOfClkPeriod(wTime, clkPeriod)
        rClkI = indexOfClkPeriod(rTime, clkPeriod)
        # isForwardEdge = wTime < rTime
        if self.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
            res = self.rtlAllocAsBuffer(allocator, dstRead)

        else:
            assert dstRead in allocator._subNodes, (
                self, allocator, "If this backedge is not buffer both write and read must be in same element")

            hasOnlyVoidData = HdlType_isVoid(self.dependsOn[0]._dtype)
            # :var dataDst: the signal which holds the value which is an output of an associated read
            # :var dataSrc: the signal which holds the value which is an input to this write
            if hasOnlyVoidData:
                dataDst = dataSrc = None
            else:
                rData: TimeIndependentRtlResource = allocator.rtlAllocHlsNetNodeOut(self.associatedRead._outputs[0])
                src = allocator.rtlAllocHlsNetNodeOut(self.dependsOn[0])
                if HdlType_isVoid(self.dependsOn[0]._dtype):
                    dataSrc = 1
                else:
                    dataSrc = src.get(wTime).data

                dataDst = rData.get(rTime).data

            # the value is not cleared properly on read if it is not written
            if dstRead.hasAnyFormOfValidPort():
                vldDst = dstRead.rtlAllocDataVldReg(allocator)
            else:
                vldDst = None

            wEn = self._getRtlEnableForNonBufferReg(allocator)
            isReg = self.allocationType == BACKEDGE_ALLOCATION_TYPE.REG
            rwMayHappenAtOnce = rClkI == wClkI or allocator.rtlStatesMayHappenConcurrently(rClkI, wClkI)
            wStageCon: ConnectionsOfStage = allocator.connections[wClkI]

            if dstRead.hasValidOnlyToPassFlags():
                assert not dstRead.src.vld._sig.drivers, (self, dstRead.src.vld._sig.drivers)
                dstRead.src.vld(1 if wEn is None else wEn)

            if wEn is None:
                res = []
                if vldDst is not None:
                    res.append(vldDst(1))
                if dataDst is not None:
                    res.append(dataDst(dataSrc))
                if isReg:
                    wStageCon.stDependentDrives.extend(res)
            else:
                if isReg:
                    if rwMayHappenAtOnce:
                        if dstRead not in allocator._subNodes:
                            raise NotImplementedError()
                        rEn = HlsNetNodeWriteBackedge._getRtlEnableForNonBufferReg(dstRead, allocator)
                    else:
                        rEn = None

                    if vldDst is not None:
                        if dataDst is not None:

                            res = If(wEn,
                                    vldDst(1),
                                    dataDst(dataSrc),
                                  )
                            if rEn is None:
                                res = res.Else(
                                        vldDst(0),
                                        dataDst(None)
                                      )
                            else:
                                res = res.Elif(rEn,
                                        vldDst(0),
                                        dataDst(None)
                                      )
                            res = [res, ]
                        else:
                            if rEn is None:
                                res = [vldDst(wEn), ]
                            else:
                                res = [vldDst(wEn | (vldDst & ~rEn)), ]

                    else:
                        if dataDst is not None:
                            res = If(wEn,
                                    dataDst(dataSrc),
                                  )
                            if rEn is None:
                                res = res.Else(
                                        dataDst(None)
                                      )
                            else:
                                res = res.Elif(rEn,
                                        dataDst(None)
                                      )
                            res = [res]
                        else:
                            res = []
                    if isReg:
                        wStageCon.stDependentDrives.extend(res)
                else:
                    assert self.allocationType == BACKEDGE_ALLOCATION_TYPE.IMMEDIATE, self.allocationType
                    if dataDst is None:
                        res = []
                    else:
                        assert dataDst._dtype == BIT, ("This was only intended for control", dataDst, dataDst._dtype)
                        res = [dataDst(dataSrc & wEn)]

                    if vldDst is not None:
                        assert vldDst._nop_val is NOT_SPECIFIED, (vldDst, vldDst._nop_val)
                        vldDst._nop_val = vldDst._dtype.from_py(0)
                        _res = vldDst(wEn)
                        wStageCon.stDependentDrives.append(_res)
                        res.append(_res)

            if self._fullPort is not None:
                if vldDst is None:
                    raise NotImplementedError()
                else:
                    if allocator._dbgAddSignalNamesToSync:
                        full = rename_signal(allocator, vldDst, f"{self.name:s}_full")
                    else:
                        full = vldDst
                    allocator.rtlRegisterOutputRtlSignal(self._fullPort, full, True, False, True)

            allocator.rtlAllocDatapathWrite(self, wStageCon, [], validHasCustomDriver=True, readyHasCustomDriver=True)

        allocator.netNodeToRtl[self] = res
        self._isRtlAllocated = True
        return res

    @override
    def debugIterShadowConnectionDst(self) -> Generator[Tuple[HlsNetNode, bool], None, None]:
        if self.associatedRead is not None:
            yield self.associatedRead, True
