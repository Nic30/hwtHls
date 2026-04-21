from _collections import deque
from typing import Union, Optional, List, Generator, Tuple, Callable

from hwt.code import Concat, If
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld, HwIOStructVld, HwIOStructRd, \
    HdlType_to_HwIO
from hwt.hwIOs.std import HwIODataRd, HwIORdVldSync, HwIOVldSync, HwIORdSync
from hwt.hwModule import HwModule
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_without_registration
from hwt.synthesizer.interfaceLevel.utils import HwIO_pack
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.frontend.ioProxyScalarHlsNetlistAgent import HlsNetlistSimAgentScalarChannelDriver, \
    HlsNetlistSimAgentScalarDriver
from hwtHls.frontend.utils import HwIO_getName
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid, HVoidData
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedTime
from hwtHls.netlist.scheduler.clk_math import clkWindowIndex, clkWindowBeginOfNext, \
    clkWindowBeginForTime
from ipCorePackager.constants import INTF_DIRECTION_asDirecton, \
    DIRECTION_opposite, DIRECTION, INTF_DIRECTION


class HlsNetNodeRead(HlsNetNodeExplicitSync):
    """
    Hls plan to read from interface or read from HLS pipeline which is binded to a buffer
    for data/sync on forward/backward edge in dataflow graph.

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed
    :ivar _isBlocking: If true the node blocks the CFG until the read is performed. If False
        the node uses flag to signalize that the read was performed and never blocks the CFG.
    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    :ivar _rawValue: A port is used only during optimization phase, its value is Concat(\\_validNB, \\_valid, dataOut)
    :ivar channelInitValues: Optional tuple for value initialization.
        (used only if this node is connected to internal channel)
    
    :ivar _rtlDataVldReg: a rtl signal or register holding data and validity signal
    :ivar _rtlFullReg: for allocationType == CHANNEL_ALLOCATION_TYPE.REG with full port this holds a register
        which is 1 if data was written (or there is init value) and not yet read
        
    """
    _PORT_ATTR_NAMES = HlsNetNodeExplicitSync._PORT_ATTR_NAMES + ["_rawValue", "_portDataOut"]

    def __init__(self, netlist: "HlsNetlistCtx", ioProxy: "IoProxy", src: Union[RtlSignal, HwIO, None],
                 dtype: Optional[HdlType]=None, name:Optional[str]=None, channelInitValues=(), addPortDataOut=True):
        # if name is None and isinstance(src, HwIO) and src._name is not None:
        #    name = src._name

        HlsNetNode.__init__(self, netlist, name=name)
        self.src = src
        self.ioProxy = ioProxy
        self.channelInitValues = channelInitValues
        self._isBlocking: bool = True
        self._rawValue: Optional[HlsNetNodeOut] = None
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self.associatedWrite: Optional["HlsNetNodeWrite"] = None

        self._initCommonPortProps(src)
        if dtype is None:
            dtype = getattr(src, "_dtype", None)
            if dtype is None:
                self._portDataOut = None  # to satisfy the assert
                d = self.getRtlDataSig()
                if d is None:
                    dtype = HVoidData
                else:
                    dtype = d._dtype

            # if isinstance(dtype, HBits) and dtype.force_vector and dtype.bit_length() == 1:
            #    raise NotImplementedError("Reading of 1b vector would cause issues"
            #                              " with missing auto casts when with other operands without force_vector", d, src)
        assert not isinstance(dtype, HBits) or dtype.signed is None, dtype
        assert dtype.isScalar(), dtype
        if addPortDataOut:
            # :note: _portDataOut should be present even if its type is void
            #        because it greatly simplifies any analysis/transformation
            self._portDataOut = self._addOutput(dtype, "dataOut")

        self._rtlDataVldReg:Optional[Union[RtlSignal, HwIO]] = None
        self._rtlFullReg:Optional[Union[RtlSignal, HwIO]] = None

    def getAssociatedWrite(self) -> Optional["HlsNetNodeWrite"]:
        return self.associatedWrite

    def setNonBlocking(self):
        self._isBlocking = False

    def getRawValue(self):
        if self._rawValue is None:
            self._rawValue = self._addOutput(HBits(self._portDataOut._dtype.bit_length() + 1), "rawValue")
        return self._rawValue

    def isChannel(self):
        return self.associatedWrite is not None

    def isBackedge(self):
        return self.associatedWrite is not None and self.associatedWrite._isBackedge

    def isForwardedge(self):
        return self.associatedWrite is not None and not self.associatedWrite._isBackedge

    @override
    def clone(self, memo:dict, keepTopPortsConnected: bool):
        y, isNew = HlsNetNodeExplicitSync.clone(self, memo, keepTopPortsConnected)
        if isNew:
            w = self.associatedWrite
            if w is not None:
                y.associatedWrite = w.clone(memo, True)
        return y, isNew

    @override
    def _removeOutput(self, i:int):
        vld = self._valid
        if vld is not None and vld.out_i == i:
            self._valid = None
        else:
            vldNb = self._validNB
            if vldNb is not None and vldNb.out_i == i:
                self._validNB = None
            else:
                rawVal = self._rawValue
                if rawVal is not None and rawVal.out_i == i:
                    self._rawValue = None
                else:
                    dataOut = self._portDataOut
                    if dataOut is not None and dataOut.out_i == i:
                        self._portDataOut = None
        return HlsNetNodeExplicitSync._removeOutput(self, i)

    @override
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = (self.extraCond, self.skipWhen)
        for i in self._inputs:
            if i not in nonOrderingInputs:
                yield i

    @override
    def hlsNetlistSimGetHandler(self, sim: "HlsNetlistSimulator") -> HlsNetlistSimAgentScalarDriver:
        if self.associatedWrite is None:
            proxy: "IoProxy" = self.ioProxy
            assert proxy is not None, self
            ag = sim.simAgentForIoProxy.get(proxy, None)
            if ag is None:
                argI, isOut = sim.topIoOrder[proxy]
                data = sim.topIoArgs[argI]
                assert not isOut, self
                ag = proxy.getHlsNetlistSimAgentDriver(data)
                sim.simAgentForIoProxy[proxy] = ag
            return ag
        else:
            data = sim.dataForChannel.get(self.associatedWrite)
            if data is None:
                data: deque[Optional[HBitsConst]] = deque()
                sim.dataForChannel[self.associatedWrite] = data
            return HlsNetlistSimAgentScalarChannelDriver(self, data)

    def _mayHappenConcurrentlyWithWrite(self) -> bool:
        w = self.associatedWrite
        assert w is not None, self
        rParent, rClkI = self.getParentSyncNode()
        rParent: "ArchElement"
        wParent, wClkI = w.getParentSyncNode()
        if rParent is wParent:
            return rClkI == wClkI or rParent.rtlStatesMayHappenConcurrently(rClkI, wClkI)
        else:
            return True

    def _rtlAllocDatapathIo(self):
        """
        Load declaration of the interface and construct its RTL signals.
        """
        if self.src and self.src._parent is not None:
            return
        hasValid = self._rtlUseValid
        hasReady = self._rtlUseReady
        # if (isinstance(self, HlsNetNodeRead) and self.associatedWrite._getBufferCapacity() == 0) or \
        #        (isinstance(self, HlsNetNodeWrite) and self._getBufferCapacity() == 0):
        #        hasValid &= self._rtlUseReady
        #        hasReady &= self._rtlUseValid

        u:HwModule = self.netlist.parentHwModule
        w = self.associatedWrite
        name = None
        if self.src is not None:
            name = self.src._name
        # assert self.src is None, (
        #    "Src interface must not be yet instantiated on parent HwModule", self, self.src)
        assert w is not None, ("if src is None this is a channel and associatedWrite must be set", self)
        assert w.dst is None or self.src, (w, w.dst)
        dtype = self._portDataOut._dtype
        if HdlType_isVoid(dtype):
            if hasValid and hasReady:
                src = HwIORdVldSync()
            elif hasValid:
                src = HwIOVldSync()
            elif hasReady:
                src = HwIORdSync()
            else:
                src = None

        else:
            if hasValid and hasReady:
                src = HwIOStructRdVld()
                src.T = dtype
            elif hasValid:
                src = HwIOStructVld()
                src.T = dtype
            elif hasReady:
                src = HwIOStructRd()
                src.T = dtype
            else:
                src = HdlType_to_HwIO().apply(dtype)

        if src is not None:
            src._name = name if name is not None else self.netlist.namePrefix + (self.name if self.name is not None else f"n{self._id}")
            self.src = HwIO_without_registration(u, src, src._name)

        allocTy = w.allocationType
        if allocTy == CHANNEL_ALLOCATION_TYPE.IMMEDIATE:
            w.dst = self.src
        elif src is None:
            w.dst = None
        else:
            wName = name if name is not None else self.netlist.namePrefix + (w.name if w.name is not None else f"n{w._id}")
            w.dst = HwIO_without_registration(u, self.src.__copy__(), wName)

    def rtlAllocChannelDataVldAndFullReg(self, allocator:"ArchElement") -> Tuple[Optional[Union[RtlSignal, HwIO]], Optional[Union[RtlSignal, HwIO]]]:
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
        dataVldReg: Optional[Union[RtlSignal, HwIO]] = None
        fullReg: Optional[Union[RtlSignal, HwIO]] = None
        srcWrite = self.associatedWrite
        dataRegName = f"{allocator.namePrefix:s}{self.name:s}"
        capacity = srcWrite._getBufferCapacity()
        if srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.REG and capacity == 1:
            hadInit = bool(self.channelInitValues)
            if hasVld:
                dataVldReg = allocator._reg(f"{dataRegName:s}_vld", BIT, def_val=int(hadInit))
                dataVldReg._isUnnamedExpr = False
            if hasFull:
                fullReg = allocator._reg(f"{dataRegName:s}_full", BIT, def_val=int(hadInit))
                fullReg._isUnnamedExpr = False
        elif srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE or capacity == 0:
            dataVldReg = allocator._sig(f"{dataRegName:s}_vld", BIT)
            assert not hasFull, self
        else:
            raise NotImplementedError(self, srcWrite.allocationType, capacity)

        for vldOut in (self._valid, self._validNB):
            if vldOut is None:
                continue
            allocator.rtlRegisterOutputRtlSignal(vldOut, dataVldReg, False, False, True)

        self._rtlDataVldReg = dataVldReg
        self._rtlFullReg = fullReg

        return dataVldReg, fullReg

    def _rtlAllocValidPorts(self, allocator: "ArchElement"):
        netNodeToRtl = allocator.netNodeToRtl
        if self._rtlUseValid:
            validRtl = self._getRtlSyncTuple()[0]
            if isinstance(validRtl, int):
                raise NotImplementedError("rtl valid should not be requested because it is constant", self)
        else:
            validRtl = BIT.from_py(1)

        _valid = None
        if self.hasValid():
            _valid = allocator.rtlRegisterOutputRtlSignal(self._valid, validRtl, False, False, False)

        if self.hasValidNB():
            if _valid is None:
                _validNB = allocator.rtlRegisterOutputRtlSignal(self._validNB, validRtl, False, False, False)
            else:
                _validNB = _valid
                netNodeToRtl[self._validNB] = _validNB

        return _valid, validRtl

    def _rtlAllocDataVoidOut(self, allocator: "ArchElement"):
        v = self._dataVoidOut._dtype.from_py(None)
        return allocator.rtlRegisterOutputRtlSignal(self._dataVoidOut, v, False, False, False)

    def _getRtlSyncTuple(self):
        return self.ioProxy._getRtlSyncTuple(self.src)

    def _getRtlSyncSignals(self):
        return self.ioProxy._getRtlSyncSignals(self.src)

    @override
    def rtlAllocAsChannel(self, allocator:"ArchElement") -> TimeIndependentRtlResource:
        """
        :note: For doc see :meth:`HlsNetNodeWriteBackedge.rtlAlloc`
        """
        assert not self._isRtlAllocated, self
        assert self._rawValue is None, ("access to a _rawValue should be already lowered and this port should be removed", self)
        dataOut = self._portDataOut
        hasNoSpecialControl = self._isBlocking and not self.hasValidNB() and not self.hasValid()
        self._rtlAllocDatapathIo()

        srcWrite = self.associatedWrite
        if srcWrite.allocationType == CHANNEL_ALLOCATION_TYPE.BUFFER:
            # allocate as a read from buffer output interface
            return self.rtlAllocAsIO(allocator)
        else:
            assert not self._isRtlAllocated, self
            # allocate as a register
            if self._dataVoidOut is not None:
                self._rtlAllocDataVoidOut(self, allocator)

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
                    dataReg._isUnnamedExpr = False
            else:
                assert srcWrite.allocationType in (CHANNEL_ALLOCATION_TYPE.IMMEDIATE,
                                                   CHANNEL_ALLOCATION_TYPE.REG), srcWrite.allocationType
                assert not init, ("Immediate channels can not have init value", srcWrite, init)
                dataReg = allocator._sig(dataRegName, dtype)

            dataVldReg, fullReg = self.rtlAllocChannelDataVldAndFullReg(allocator)

            dstRead = self
            clkPeriod = self.netlist.normalizedClkPeriod
            rClkI = clkWindowIndex(dstRead.scheduledOut[0], clkPeriod)
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
                        # en = allocator._rtlAllocDatapathGetIoAck(self, allocator.namePrefix)
                        en = allocator.rtlAllocHlsNetNodeInDriverIfExists(self.extraCond)
                        if en is not None:
                            res = [If(en.data, res), ]
                        # rStageCon.stateChangeDependentDrives.append(res)

            if  dataVldReg is not None:
                if self._rtlUseValid:
                    assert not self.src.vld._sig._rtlDrivers, (self, self.src.vld._sig._rtlDrivers)
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

    @override
    def rtlAllocAsIO(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        """
        Instantiate read operation on RTL level
        """
        assert not self._isRtlAllocated, self
        if self.associatedWrite is not None:
            self._rtlAllocDatapathIo()

        r_out = self._portDataOut
        hasNoSpecialControl = self._isBlocking and not self.hasValidNB() and not self.hasValid() and self._dataVoidOut is None
        # netNodeToRtl = allocator.netNodeToRtl

        if self.hasReady() or self.hasReadyNB():
            raise AssertionError("Ready of read is always 1 and this port should be already optimized out")

        hasData = not HdlType_isVoid(r_out._dtype)
        if hasData:
            assert not isinstance(self.src, (MultiPortGroup, BankedPortGroup)), (
                "At this point the concrete memory port should be resolved for this IO node", self)
            dataRtl = self.getRtlDataSig()
            assert dataRtl is not None, self
            _data = allocator.rtlRegisterOutputRtlSignal(r_out, dataRtl, False, False, False)
        else:
            dataRtl = None
            _data = []

        if self.hasAnyUsedValidPort():
            self._rtlAllocValidPorts(allocator)

        if self._dataVoidOut is not None:
            self._rtlAllocDataVoidOut(allocator)

        assert self._rawValue is None, ("access to a _rawValue should be already lowered and this port should be removed", self)

        # because there are multiple outputs
        clkI = clkWindowIndex(self.scheduledOut[0], allocator.netlist.normalizedClkPeriod)
        if self._rtlUseReady:
            if self.src is None:
                rtlReadySignal = None
            else:
                _, rtlReadySignal = self._getRtlSyncTuple()
                if rtlReadySignal == 1:
                    rtlReadySignal = None
            allocator.rtlAllocDatapathRead(self, rtlReadySignal, allocator.connections[clkI], [])

        for sync, time in zip(self.dependsOn, self.scheduledIn):
            if HdlType_isVoid(sync._dtype):
                continue
            assert isinstance(sync, HlsNetNodeOut), (self, self.dependsOn)
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only data path
            allocator.rtlAllocHlsNetNodeOutInTime(sync, time)

        self._isRtlAllocated = True
        return _data if hasNoSpecialControl else []

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        if self.isChannel():
            return self.rtlAllocAsChannel(allocator)
        else:
            return self.rtlAllocAsIO(allocator)

    def getSchedulingResourceType(self):
        resourceType = self.src
        # assert resourceType is not None, self
        if resourceType is None:
            return self
        return resourceType

    @override
    def checkScheduling(self):
        HlsNetNodeExplicitSync.checkScheduling(self)
        resourceType = self.getSchedulingResourceType()
        if resourceType is not None:
            clkI = self.getSchedResourceClkI()
            assert self.netlist.scheduler.resourceUsage[clkI].get(resourceType, None) is not None, (
                self, clkI, self.netlist.scheduler.resourceUsage)

    @override
    def resetScheduling(self):
        scheduledZero = self.scheduledZero
        if scheduledZero is None:
            return  # already not scheduled
        resourceType = self.getSchedulingResourceType()
        if resourceType is not None:
            self.netlist.scheduler.resourceUsage.removeUse(resourceType, self.getSchedResourceClkI())
        HlsNetNodeExplicitSync.resetScheduling(self)

    @override
    def setScheduling(self, schedule:SchedulizationDict):
        resourceUsage = self.netlist.scheduler.resourceUsage
        resourceType = self.getSchedulingResourceType()
        if resourceType is not None and self.scheduledZero is not None:
            resourceUsage.removeUse(resourceType, self.getSchedResourceClkI())

        HlsNetNodeExplicitSync.setScheduling(self, schedule)
        if resourceType is not None:
            self.netlist.scheduler.resourceUsage.addUse(resourceType, self.getSchedResourceClkI())

    @override
    def moveSchedulingTime(self, offset: SchedTime):
        originalClkI = self.getSchedResourceClkI()
        HlsNetNode.moveSchedulingTime(self, offset)

        curClkI = self.getSchedResourceClkI()
        if originalClkI != curClkI:
            resourceType = self.getSchedulingResourceType()
            self.netlist.scheduler.resourceUsage.moveUse(resourceType, originalClkI, curClkI)

    @override
    def scheduleAsap(self, pathForDebug: Optional[SetList["HlsNetNode"]], beginOfFirstClk: int,
                     outputTimeGetter: Optional[OutputTimeGetter],
                     isRead=True) -> List[int]:
        # schedule all dependencies
        if self.scheduledZero is None:
            HlsNetNode.scheduleAsap(self, pathForDebug, beginOfFirstClk, outputTimeGetter)
            netlist = self.netlist
            clkPeriod = netlist.normalizedClkPeriod
            scheduledZero = self.scheduledZero

            minTime = None
            if isRead:
                # optionaly move to next clock cycle because we can not allow write to be in the same clock cycle as read
                # for forward edges allocated as REG
                w = self.associatedWrite
                if w is not None and\
                        w.isForwardedge() and\
                        w.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
                    w.scheduleAsap(pathForDebug, beginOfFirstClk, outputTimeGetter)
                    minTime = clkWindowBeginOfNext(w.scheduledZero, clkPeriod)
            # else:
            #    r = self.associatedRead
            #    if r is not None and\
            #            self.isBackedge() and\
            #            self.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
            #        r.scheduleAsap(pathForDebug, beginOfFirstClk, outputTimeGetter)
            #        minTime = clkWindowBeginOfNext(r.scheduledZero, clkPeriod)
            curClkI = self.getSchedResourceClkI()
            if minTime is not None and scheduledZero < minTime:
                scheduledZero = minTime
                t = minTime
                curClkI = max(minTime // clkPeriod, curClkI)
            else:
                t = None

            resourceType = self.getSchedulingResourceType()
            scheduler = netlist.scheduler
            epsilon = scheduler.epsilon
            if resourceType is not None:
                suitableClkI = scheduler.resourceUsage.findFirstClkISatisfyingLimit(resourceType, curClkI)
                if curClkI != suitableClkI:
                    # move to next clock cycle if IO constraint requires it
                    t = suitableClkI * clkPeriod + epsilon + max(self.inputWireDelay, default=0)

                scheduler.resourceUsage.addUse(resourceType, suitableClkI)

            if t is not None:
                if self.isMulticlock:
                    ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
                    self._setScheduleZeroTimeMultiClock(t, clkPeriod, epsilon, ffdelay)
                else:
                    self._setScheduleZeroTimeSingleClock(t)

            assert self.scheduledOut is not None, self

        return self.scheduledOut

    @override
    def scheduleAlapCompaction(self,
                               endOfLastClk: SchedTime,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]],
                               isRead=True):
        originalTimeZero = self.scheduledZero
        netlist = self.netlist
        scheduler = netlist.scheduler
        clkPeriod = netlist.normalizedClkPeriod
        resourceType = self.getSchedulingResourceType()
        originalClkI = self.getSchedResourceClkI()
        epsilon = scheduler.epsilon
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, scheduler.resolution)

        if self.isBackedge() and not self._inputs and not any(self.usedBy):
            # use time from backedge because this node is not connected to anything and floating freely in time
            raise AssertionError("The node must have at least ordering connection to write, it can not just freely float in time", self)

        maxTime = None
        if not isRead:
            if self.associatedRead is not None and\
                    self.isForwardedge() and\
                    self.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
                # optionaly move to prev clock cycle because we can not allow write to be in the same clock cycle as read
                for _ in self.associatedRead.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter, excludeNode):
                    pass
                maxTime = clkWindowBeginForTime(self.associatedRead.scheduledZero, clkPeriod) - epsilon

        for _ in HlsNetNodeExplicitSync.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter, excludeNode):
            pass

        scheduledZero = self.scheduledZero
        curClkI = self.getSchedResourceClkI()
        if maxTime is not None and maxTime < scheduledZero:
            t = maxTime
            curClkI = self._getSchedResourceClkI(t)
            if not self.realization.isAllowedInFFStoreTime:
                t -= ffdelay
        else:
            t = None

        if resourceType is not None:
            if originalClkI != curClkI:
                scheduler.resourceUsage.moveUse(resourceType, originalClkI, curClkI)

                suitableClkI = scheduler.resourceUsage.findFirstClkISatisfyingLimitEndToStart(resourceType, curClkI)

                if curClkI != suitableClkI:
                    # move to prev clock cycle if IO constraint requires it
                    t = (suitableClkI + 1) * clkPeriod - ffdelay
                    scheduler.resourceUsage.moveUse(resourceType, curClkI, suitableClkI)

        if t is not None:
            if self.isMulticlock:
                self._setScheduleZeroTimeMultiClock(t, clkPeriod, epsilon, ffdelay)
            else:
                self._setScheduleZeroTimeSingleClock(t)

        if originalTimeZero != self.scheduledZero:
            assert originalTimeZero < self.scheduledZero, (self, originalTimeZero, self.scheduledZero,
                "Node can not be resolved to earlier ALAP time, it would mean that the original schedule was wrong")
            for dep in self.dependsOn:
                yield dep.obj

    def _getRtlDataSig(self, src: Union[HwIO, tuple, RtlSignalBase]) -> RtlSignal:
        if isinstance(src, RtlSignalBase):
            return src
        elif isinstance(src, (tuple, HwIOArray)):
            return Concat(*(self._getRtlDataSig(v) for v in reversed(src)))
        else:
            exclude = self.ioProxy._getRtlSyncSignals(src)

            if isinstance(src, HwIODataRd):
                if src.rd._direction == INTF_DIRECTION.UNKNOWN:
                    masterDirEqTo = src._masterDir
                else:
                    masterDirEqTo = DIRECTION_opposite[INTF_DIRECTION_asDirecton[src.rd._direction]]
            else:
                if exclude:
                    assert exclude[0]._masterDir == DIRECTION.OUT, (exclude[0]._masterDir, self)
                    masterDirEqTo = exclude[0]._masterDir
                else:
                    masterDirEqTo = src._masterDir

            return HwIO_pack(src,
                            masterDirEqTo=masterDirEqTo,
                            exclude=exclude)

    def getRtlDataSig(self) -> Optional[RtlSignal]:
        src = self.src
        assert src is not None, ("This operation is missing hw interface or it is only virtual and does not use any data signals", self)
        res = self._getRtlDataSig(src)
        if res is not None:
            assert isinstance(res._dtype, HBits), (res, res._dtype)
            if res._dtype.signed is not None:
                res = res._reinterpret_cast(HBits(res._dtype.bit_length()))
            if isinstance(res, RtlSignalBase) and res._hasGenericName:
                name = self.name
                if name is None:
                    name = f"r{self._id}_data"
                res._name = name

        if self._portDataOut is not None:
            assert res is not None, self
            outTy = self._portDataOut._dtype
            resTy = res._dtype
            assert outTy == resTy or outTy.bit_length() == resTy.bit_length(), (self._portDataOut, outTy, resTy)
        return res

    def _getInterfaceName(self, io: Union[HwIO, Tuple[HwIO]]) -> str:
        return HwIO_getName(self.netlist.parentHwModule, io)

    def __repr__(self):
        srcName = "<None>" if self.src is None else self._getInterfaceName(self.src)
        return (f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}"
               f"{' ' + self.name if self.name else ''} {self._stringFormatRtlUseReadyAndValid():s} {srcName:s}>")

