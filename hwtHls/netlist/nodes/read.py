from typing import Union, Optional, List, Generator, Tuple, Callable

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
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
from hwtHls.architecture.syncUtils import HwIO_getSyncTuple, \
    HwIO_getSyncSignals
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.frontend.utils import HwIO_getName
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid, HVoidData
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from ipCorePackager.constants import INTF_DIRECTION_asDirecton, \
    DIRECTION_opposite, DIRECTION, INTF_DIRECTION


class HlsNetNodeRead(HlsNetNodeExplicitSync):
    """
    Hls plan to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed
    :ivar _isBlocking: If true the node blocks the CFG until the read is performed. If False
        the node uses flag to signalize that the read was performed and never blocks the CFG.
    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    :ivar _rawValue: A port is used only during optimization phase, its value is Concat(\\_validNB, \\_valid, dataOut)
    :ivar channelInitValues: Optional tuple for value initialization.
        (used only if this node is connected to internal channel)
    """
    _PORT_ATTR_NAMES = HlsNetNodeExplicitSync._PORT_ATTR_NAMES + ["_rawValue", "_portDataOut"]

    def __init__(self, netlist: "HlsNetlistCtx", src: Union[RtlSignal, HwIO, None],
                 dtype: Optional[HdlType]=None, name:Optional[str]=None, channelInitValues=(), addPortDataOut=True):
        HlsNetNode.__init__(self, netlist, name=name)
        self.src = src
        self.channelInitValues = channelInitValues
        self._isBlocking: bool = True
        self._rawValue: Optional[HlsNetNodeOut] = None
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self.associatedWrite: Optional["HlsNetNodeWrite"] = None

        self._initCommonPortProps(src)
        if dtype is None:
            d = self.getRtlDataSig()
            if d is None:
                dtype = HVoidData
            else:
                dtype = d._dtype

            # if isinstance(dtype, HBits) and dtype.force_vector and dtype.bit_length() == 1:
            #    raise NotImplementedError("Reading of 1b vector would cause issues"
            #                              " with missing auto casts when with other operands without force_vector", d, src)
        assert not isinstance(dtype, HBits) or dtype.signed is None, dtype
        if addPortDataOut:
            self._portDataOut = self._addOutput(dtype, "dataOut")

    def getAssociatedWrite(self) -> Optional["HlsNetNodeWrite"]:
        return self.associatedWrite

    def setNonBlocking(self):
        self._isBlocking = False

    def getRawValue(self):
        if self._rawValue is None:
            self._rawValue = self._addOutput(HBits(self._portDataOut._dtype.bit_length() + 1), "rawValue")
        return self._rawValue

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

    def _rtlAllocDatapathIo(self):
        """
        Load declaration of the interface and construct its RTL signals.
        """
        if self.src is None:
            hasValid = self._rtlUseValid
            hasReady = self._rtlUseReady
            # if (isinstance(self, HlsNetNodeRead) and self.associatedWrite._getBufferCapacity() == 0) or \
            #        (isinstance(self, HlsNetNodeWrite) and self._getBufferCapacity() == 0):
            #        hasValid &= self._rtlUseReady
            #        hasReady &= self._rtlUseValid

            u:HwModule = self.netlist.parentHwModule
            assert self.src is None, (
                "Src interface must not be yet instantiated on parent HwModule", self, self.src)
            w = self.associatedWrite
            assert w.dst is None, (w, w.dst)
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
                src._name = self.netlist.namePrefix + (self.name if self.name is not None else f"n{self._id}")
                self.src = HwIO_without_registration(u, src, src._name)

            allocTy = w.allocationType
            if allocTy == CHANNEL_ALLOCATION_TYPE.IMMEDIATE:
                w.dst = self.src
            elif src is None:
                w.dst = None
            else:
                w.dst = HwIO_without_registration(u, self.src.__copy__(), self.netlist.namePrefix + (w.name if w.name is not None else f"n{w._id}"))

    def _rtlAllocValidPorts(self, allocator: "ArchElement"):
        netNodeToRtl = allocator.netNodeToRtl
        if self._rtlUseValid:
            validRtl = HwIO_getSyncTuple(self.src)[0]
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

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
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
        clkI = indexOfClkPeriod(self.scheduledOut[0], allocator.netlist.normalizedClkPeriod)
        if self.src is None:
            rtlReadySignal = None
        else:
            _, rtlReadySignal = HwIO_getSyncTuple(self.src)
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

    def getSchedulingResourceType(self):
        resourceType = self.src
        # assert resourceType is not None, self
        return resourceType

    @override
    def checkScheduling(self):
        HlsNetNodeExplicitSync.checkScheduling(self)
        resourceType = self.getSchedulingResourceType()
        if resourceType is not None:
            clkPeriod = self.netlist.normalizedClkPeriod
            clkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
            assert self.netlist.scheduler.resourceUsage[clkI].get(resourceType, None) is not None, (
                self, clkI, self.netlist.scheduler.resourceUsage)

    @override
    def resetScheduling(self):
        scheduledZero = self.scheduledZero
        if scheduledZero is None:
            return  # already restarted
        resourceType = self.getSchedulingResourceType()
        if resourceType is not None:
            clkPeriod = self.netlist.normalizedClkPeriod
            self.netlist.scheduler.resourceUsage.removeUse(resourceType, indexOfClkPeriod(scheduledZero, clkPeriod))
        HlsNetNodeExplicitSync.resetScheduling(self)

    @override
    def setScheduling(self, schedule:SchedulizationDict):
        resourceUsage = self.netlist.scheduler.resourceUsage
        resourceType = self.getSchedulingResourceType()
        if resourceType is not None:
            clkPeriod = self.netlist.normalizedClkPeriod

            if self.scheduledZero is not None:
                resourceUsage.removeUse(resourceType, indexOfClkPeriod(self.scheduledZero, clkPeriod))

        HlsNetNodeExplicitSync.setScheduling(self, schedule)
        if resourceType is not None:
            self.netlist.scheduler.resourceUsage.addUse(resourceType, indexOfClkPeriod(self.scheduledZero, clkPeriod))

    @override
    def moveSchedulingTime(self, offset: SchedTime):
        clkPeriod = self.netlist.normalizedClkPeriod
        originalClkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
        HlsNetNode.moveSchedulingTime(self, offset)

        curClkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
        if originalClkI != curClkI:
            resourceType = self.getSchedulingResourceType()
            self.netlist.scheduler.resourceUsage.moveUse(resourceType, originalClkI, curClkI)

    @override
    def scheduleAsap(self, pathForDebug: Optional[SetList["HlsNetNode"]], beginOfFirstClk: int,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        # schedule all dependencies
        if self.scheduledOut is None:
            HlsNetNode.scheduleAsap(self, pathForDebug, beginOfFirstClk, outputTimeGetter)
            scheduledZero = self.scheduledZero
            clkPeriod = self.netlist.normalizedClkPeriod
            curClkI = scheduledZero // clkPeriod
            resourceType = self.getSchedulingResourceType()
            if resourceType is not None:
                scheduler = self.netlist.scheduler
                suitableClkI = scheduler.resourceUsage.findFirstClkISatisfyingLimit(resourceType, curClkI)
                if curClkI != suitableClkI:
                    # move to next clock cycle if IO constraint requires it
                    epsilon = scheduler.epsilon
                    t = suitableClkI * clkPeriod + epsilon + max(self.inputWireDelay, default=0)
                    if self.isMulticlock:
                        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
                        self._setScheduleZeroTimeMultiClock(t, clkPeriod, epsilon, ffdelay)
                    else:
                        self._setScheduleZeroTimeSingleClock(t)

                scheduler.resourceUsage.addUse(resourceType, suitableClkI)
            assert self.scheduledOut is not None, self

        return self.scheduledOut

    @override
    def scheduleAlapCompaction(self,
                               endOfLastClk: SchedTime,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]):
        originalTimeZero = self.scheduledZero
        netlist = self.netlist
        scheduler = netlist.scheduler
        clkPeriod = netlist.normalizedClkPeriod
        resourceType = self.getSchedulingResourceType()
        originalClkI = indexOfClkPeriod(originalTimeZero, clkPeriod)
        if self.isMulticlock:
            for _ in HlsNetNodeExplicitSync.scheduleAlapCompactionMultiClock(self, endOfLastClk, outputMinUseTimeGetter, excludeNode):
                pass
        else:
            for _ in HlsNetNodeExplicitSync.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter, excludeNode):
                pass

        curClkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
        if resourceType is not None:
            if originalClkI != curClkI:
                scheduler.resourceUsage.moveUse(resourceType, originalClkI, curClkI)

                suitableClkI = scheduler.resourceUsage.findFirstClkISatisfyingLimitEndToStart(resourceType, curClkI)

                if curClkI != suitableClkI:
                    # move to next clock cycle if IO constraint requires it
                    ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, scheduler.resolution)
                    t = (suitableClkI + 1) * clkPeriod - ffdelay
                    if self.isMulticlock:
                        epsilon = scheduler.epsilon
                        self._setScheduleZeroTimeMultiClock(t, clkPeriod, epsilon, ffdelay)
                    else:
                        self._setScheduleZeroTimeSingleClock(t)

                    scheduler.resourceUsage.moveUse(resourceType, curClkI, suitableClkI)

        if originalTimeZero != self.scheduledZero:
            assert originalTimeZero < self.scheduledZero, (self, originalTimeZero, self.scheduledZero)
            for dep in self.dependsOn:
                yield dep.obj

    def getRtlDataSig(self) -> Optional[RtlSignal]:
        src: HwIO = self.src
        assert src is not None, ("This operation is missing hw interface or it is only virtual and does not use any data signals", self)
        if isinstance(src, RtlSignalBase):
            res = src
        else:
            exclude = HwIO_getSyncSignals(src)

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

            res = HwIO_pack(src,
                            masterDirEqTo=masterDirEqTo,
                            exclude=exclude)
        if res is not None:
            assert isinstance(res._dtype, HBits), (res, res._dtype)
            if res._dtype.signed is not None:
                res = res._reinterpret_cast(HBits(res._dtype.bit_length()))
            if isinstance(res, RtlSignalBase) and res.hasGenericName:
                name = self.name
                if name is None:
                    name = f"r{self._id}_data"
                res._name = name

        return res

    def _getInterfaceName(self, io: Union[HwIO, Tuple[HwIO]]) -> str:
        return HwIO_getName(self.netlist.parentHwModule, io)

    def __repr__(self):
        return (f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}"
               f"{' ' + self.name if self.name else ''} {self._stringFormatRtlUseReadyAndValid():s} {self.src}>")

