from typing import Union, Optional, List, Generator, Tuple

from hwt.code import Concat
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.std import RdSynced
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import packIntf
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.syncUtils import getInterfaceSyncTuple, \
    getInterfaceSyncSignals
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.frontend.utils import getInterfaceName
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid, HVoidData
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    HlsNetNodeOutAny
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.typingFuture import override
from hwtLib.handshaked.streamNode import InterfaceOrValidReadyTuple
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
    :ivar _rawValue: A port is used only during optimization phase, its value is Concat(_validNB, _valid, dataOut)
    """

    def __init__(self, netlist: "HlsNetlistCtx", src: Union[RtlSignal, Interface],
                 dtype: Optional[HdlType]=None, name:Optional[str]=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self.src = src
        self.maxIosPerClk: int = 1
        self._isBlocking: bool = True
        self._rawValue: Optional[HlsNetNodeOut] = None
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self._initCommonPortProps(src)
        if dtype is None:
            d = self.getRtlDataSig()
            if d is None:
                dtype = HVoidData
            else:
                dtype = d._dtype

            # if isinstance(dtype, Bits) and dtype.force_vector and dtype.bit_length() == 1:
            #    raise NotImplementedError("Reading of 1b vector would cause issues"
            #                              " with missing auto casts when with other operands without force_vector", d, src)

        self._addOutput(dtype, "dataOut")

    def setNonBlocking(self):
        self._isBlocking = False

    def getRawValue(self):
        if self._rawValue is None:
            self._rawValue = self._addOutput(Bits(self._outputs[0]._dtype.bit_length() + 1), "rawValue")
        return self._rawValue

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
        return HlsNetNodeExplicitSync._removeOutput(self, i)

    @override
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = (self.extraCond, self.skipWhen, self._inputOfCluster, self._outputOfCluster)
        for i in self._inputs:
            if i not in nonOrderingInputs:
                yield i

    def getRtlValidSig(self, intf: InterfaceOrValidReadyTuple) -> Union[RtlSignalBase, HValue]:
        vld = getInterfaceSyncTuple(intf)[0]
        if isinstance(vld, int):
            raise NotImplementedError("rtl valid should not be requested because it is constant", self)
        else:
            return vld

    def _rtlAllocDataVoidOut(self, allocator: "ArchElement"):
        v = self._dataVoidOut._dtype.from_py(None)
        return allocator.rtlRegisterOutputRtlSignal(self._dataVoidOut, v, False, False, False)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        """
        Instantiate read operation on RTL level
        """
        assert not self._isRtlAllocated, self
        r_out = self._outputs[0]
        hasNoSpecialControl = self._isBlocking and not self.hasValidNB() and not self.hasValid() and self._dataVoidOut is None
        netNodeToRtl = allocator.netNodeToRtl

        if self.hasReady() or self.hasReadyNB():
            raise AssertionError("Ready of read is always 1 and this port should be already optimized out")

        hasData = not HdlType_isVoid(r_out._dtype)
        if hasData:
            assert not isinstance(self.src, (MultiPortGroup, BankedPortGroup)), (
                "At this point the concrete memory port should be resolved for this IO node", self)
            dataRtl = self.getRtlDataSig()
            _data = allocator.rtlRegisterOutputRtlSignal(r_out, dataRtl, False, False, False)
        else:
            dataRtl = None
            _data = []

        for sync, time in zip(self.dependsOn, self.scheduledIn):
            if HdlType_isVoid(sync._dtype):
                continue
            assert isinstance(sync, HlsNetNodeOut), (self, self.dependsOn)
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only data path
            allocator.rtlAllocHlsNetNodeOutInTime(sync, time)

        _valid = None
        _validNB = None
        if self.hasAnyUsedValidPort():
            validRtl = self.getRtlValidSig(self.src)
            if self.hasValid():
                _valid = allocator.rtlRegisterOutputRtlSignal(self._valid, validRtl, False, False, False)
            if self.hasValidNB():
                if _valid is None:
                    _validNB = allocator.rtlRegisterOutputRtlSignal(self._validNB, validRtl, False, False, False)
                else:
                    _validNB = _valid
                    netNodeToRtl[self._validNB] = _validNB

        if self._dataVoidOut is not None:
            self._rtlAllocDataVoidOut(allocator)

        if self._rawValue is not None:
            assert not self._isBlocking, self
            assert self.hasValid(), self
            if hasData:
                if hasData:
                    rawValue = Concat(validRtl, validRtl, dataRtl)
                else:
                    rawValue = Concat(validRtl, validRtl)

                allocator.rtlRegisterOutputRtlSignal(self._rawValue, rawValue, False, False, False)

            else:
                if self.hasValidNB():
                    rawValue = Concat(validRtl, validRtl)
                    allocator.rtlRegisterOutputRtlSignal(self._rawValue, rawValue, False, False, False)

                else:
                    netNodeToRtl[self._rawValue] = _valid

        # because there are multiple outputs
        clkI = indexOfClkPeriod(self.scheduledOut[0], allocator.netlist.normalizedClkPeriod)
        allocator.rtlAllocDatapathRead(self, allocator.connections[clkI], [])

        self._isRtlAllocated = True
        return _data if hasNoSpecialControl else []

    def getSchedulingResourceType(self):
        resourceType = self.src
        assert resourceType is not None, self
        return resourceType

    @override
    def checkScheduling(self):
        HlsNetNodeExplicitSync.checkScheduling(self)
        resourceType = self.getSchedulingResourceType()
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
        clkPeriod = self.netlist.normalizedClkPeriod
        self.netlist.scheduler.resourceUsage.removeUse(resourceType, indexOfClkPeriod(scheduledZero, clkPeriod))
        HlsNetNodeExplicitSync.resetScheduling(self)

    @override
    def setScheduling(self, schedule:SchedulizationDict):
        resourceUsage = self.netlist.scheduler.resourceUsage
        resourceType = self.getSchedulingResourceType()
        clkPeriod = self.netlist.normalizedClkPeriod

        if self.scheduledZero is not None:
            resourceUsage.removeUse(resourceType, indexOfClkPeriod(self.scheduledZero, clkPeriod))

        HlsNetNodeExplicitSync.setScheduling(self, schedule)
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
    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]], beginOfFirstClk: int,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        # schedule all dependencies
        if self.scheduledOut is None:
            HlsNetNode.scheduleAsap(self, pathForDebug, beginOfFirstClk, outputTimeGetter)
            scheduledZero = self.scheduledZero
            clkPeriod = self.netlist.normalizedClkPeriod
            curClkI = scheduledZero // clkPeriod
            resourceType = self.getSchedulingResourceType()
            scheduler = self.netlist.scheduler
            suitableClkI = scheduler.resourceUsage.findFirstClkISatisfyingLimit(resourceType, curClkI, self.maxIosPerClk)
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

        return self.scheduledOut

    @override
    def scheduleAlapCompaction(self, endOfLastClk: SchedTime, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        originalTimeZero = self.scheduledZero
        netlist = self.netlist
        scheduler = netlist.scheduler
        clkPeriod = netlist.normalizedClkPeriod
        resourceType = self.getSchedulingResourceType()
        originalClkI = indexOfClkPeriod(originalTimeZero, clkPeriod)
        if self.isMulticlock:
            for _ in HlsNetNodeExplicitSync.scheduleAlapCompactionMultiClock(self, endOfLastClk, outputMinUseTimeGetter):
                pass
        else:
            for _ in HlsNetNodeExplicitSync.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter):
                pass

        curClkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
        if originalClkI != curClkI:
            scheduler.resourceUsage.moveUse(resourceType, originalClkI, curClkI)

        suitableClkI = scheduler.resourceUsage.findFirstClkISatisfyingLimitEndToStart(resourceType, curClkI, self.maxIosPerClk)
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
        src: Interface = self.src
        assert src is not None, ("This operation is missing hw interface or it is only virtual and does not use any data signals", self)
        if isinstance(src, RtlSignalBase):
            res = src
        else:
            exclude = getInterfaceSyncSignals(src)

            if isinstance(src, RdSynced):
                if src.rd._direction == INTF_DIRECTION.UNKNOWN:
                    masterDirEqTo = DIRECTION.OUT
                else:
                    masterDirEqTo = DIRECTION_opposite[INTF_DIRECTION_asDirecton[src.rd._direction]]
            else:
                if exclude:
                    assert exclude[0]._masterDir == DIRECTION.OUT, (exclude[0]._masterDir, self)
                    masterDirEqTo = exclude[0]._masterDir
                else:
                    masterDirEqTo = DIRECTION.OUT

            res = packIntf(src,
                            masterDirEqTo=masterDirEqTo,
                            exclude=exclude)
        if res is not None:
            assert isinstance(res._dtype, Bits), (res, res._dtype)
            if res._dtype.signed is not None:
                res = res._reinterpret_cast(Bits(res._dtype.bit_length()))
            if isinstance(res, RtlSignalBase) and res.hasGenericName:
                name = self.name
                if name is None:
                    name = f"r{self._id}_data"
                res.name = name

        return res

    def _stringFormatRtlUseReadyAndValid(self):
        validIsOnFlag = self.hasValidOnlyToPassFlags()
        readyIsOnFlag = self.hasReadyOnlyToPassFlags()
        if self._rtlUseReady and self._rtlUseValid:
            return "<r, v>"
        elif self._rtlUseReady:
            if validIsOnFlag:
                return "<r,v(flagOnly)>"
            else:
                return "<r>"
        elif self._rtlUseValid:
            if readyIsOnFlag:
                return "<r(flagOnly), v>"
            else:
                return "<v>"
        else:
            if readyIsOnFlag and validIsOnFlag:
                return "<r(flagOnly), v(flagOnly)>"
            elif readyIsOnFlag:
                return "<r(flagOnly)>"
            elif validIsOnFlag:
                return "<v(flagOnly)>"
            else:
                return "<>"

    def _getInterfaceName(self, io: Union[Interface, Tuple[Interface]]) -> str:
        return getInterfaceName(self.netlist.parentUnit, io)

    def __repr__(self):
        return (f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}"
               f"{' ' + self.name if self.name else ''} {self._stringFormatRtlUseReadyAndValid():s} {self.src}>")


class HlsNetNodeReadIndexed(HlsNetNodeRead):
    """
    Same as :class:`~.HlsNetNodeRead` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src:Union[RtlSignal, Interface], name:Optional[str]=None):
        HlsNetNodeRead.__init__(self, netlist, src, name=name)
        self.indexes = [self._addInput("index0"), ]

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeRead.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y.indexes = [y._inputs[i.in_i] for i in self.indexes]

        return y, isNew

    @override
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = (self.extraCond, self.skipWhen, self._inputOfCluster, self._outputOfCluster, *self.indexes)
        for i in self._inputs:
            if i not in nonOrderingInputs:
                yield i

    @staticmethod
    def _strFormatIndexes(indexes: List[HlsNetNodeIn]):
        if indexes:
            indexesStrs = []
            for i in indexes:
                i: HlsNetNodeIn
                dep: Optional[HlsNetNodeOutAny] = i.obj.dependsOn[i.in_i]
                if isinstance(dep, HlsNetNodeOut):
                    indexesStrs.append(f"<{dep.obj._id:d}>.{dep.out_i:d}")
                else:
                    indexesStrs.append(repr(dep))

            return f"[{','.join(indexesStrs)}]"
        else:
            return ""

    def __repr__(self):
        return (f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''}"
               f" {self._stringFormatRtlUseReadyAndValid():s} {self.src}{self._strFormatIndexes(self.indexes)}>")
