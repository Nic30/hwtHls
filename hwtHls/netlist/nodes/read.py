from typing import Union, Optional, List, Generator, Tuple

from hwt.code import Concat
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Signal, HandshakeSync, Handshaked, VldSynced, \
    RdSynced, BramPort_withoutClk
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import packIntf
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    INVARIANT_TIME
from hwtHls.frontend.utils import getInterfaceName
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HdlType_isNonData, HdlType_isVoid, \
    HVoidData
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    HlsNetNodeOutAny
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, OutputTimeGetter, \
    OutputMinUseTimeGetter
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtLib.amba.axi_intf_common import Axi_hs
from ipCorePackager.constants import INTF_DIRECTION_asDirecton, \
    DIRECTION_opposite, DIRECTION


class HlsNetNodeRead(HlsNetNodeExplicitSync):
    """
    Hls plan to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed
    :ivar _isBlocking: If true the node blocks the CFG until the read is performed. If False
        the node uses flag to signalize that the read was performed and never blocks the CFG.
    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    :ivar _valid: output with "valid" signal for reads which signalizes that the read was successful.
                 Reading of this port requires read to be performed.
    :ivar _validNB: same as "_valid" but reading this does not cause read from main interface
    :note: _valid and _validNB holds the same, the _validNB can be read without triggering read, _valid can not because _valid is a part of the data.
    :ivar _rawValue: Concat(_validNB, _valid, dataOut)
    """

    def __init__(self, netlist: "HlsNetlistCtx", src: Union[RtlSignal, Interface], dtype: Optional[HdlType]=None, name:Optional[str]=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self.src = src
        self.maxIosPerClk = 1
        self._isBlocking = True
        self._valid = None
        self._validNB = None
        self._rawValue = None
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None

        self._initCommonPortProps()
        if dtype is None:
            d = self.getRtlDataSig()
            if d is None:
                dtype = HVoidData
            else:
                dtype = d._dtype
        self._addOutput(dtype, "dataOut")

    def setNonBlocking(self):
        self._isBlocking = False
        self._rawValue = self._addOutput(Bits(self._outputs[0]._dtype.bit_length() + 1), "rawValue")
        if self._valid is None:
            self._addValid()
        if self._validNB is None:
            self._addValidNB()

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

    def _addValid(self):
        assert self._valid is None, (self, "Already present")
        self._valid = self._addOutput(BIT, "valid")

    def _addValidNB(self):
        assert self._validNB is None, (self, "Already present")
        self._validNB = self._addOutput(BIT, "validNB")

    def getValid(self):
        if not self.hasValid():
            self._addValid()

        return self._valid

    def getValidNB(self):
        if not self.hasValidNB():
            self._addValidNB()

        return self._validNB

    def hasValid(self):
        return self._valid is not None

    def hasValidNB(self):
        return self._validNB is not None

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        nonOrderingInputs = (self.extraCond, self.skipWhen, self._inputOfCluster, self._outputOfCluster)
        for i in self._inputs:
            if i not in nonOrderingInputs:
                yield i

    def getRtlValidSig(self, allocator: "ArchElement") -> Union[RtlSignalBase, HValue]:
        intf = self.src
        if isinstance(intf, Axi_hs):
            return intf.valid._sig
        elif isinstance(intf, (Handshaked, HandshakeSync, VldSynced)):
            return intf.vld._sig
        elif isinstance(intf, (Signal, RtlSignalBase, RdSynced)):
            return BIT.from_py(1)
        elif isinstance(intf, BramPort_withoutClk):
            return intf.en._sig
        else:
            raise NotImplementedError(intf)

    def _allocateRtlInstanceDataVoidOut(self, allocator: "ArchElement"):
        netNodeToRtl = allocator.netNodeToRtl
        netNodeToRtl[self._dataVoidOut] = TimeIndependentRtlResource(
            self._dataVoidOut._dtype.from_py(None),
            INVARIANT_TIME,
            allocator,
            False)

    def allocateRtlInstance(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        """
        Instantiate read operation on RTL level
        """
        r_out = self._outputs[0]
        hasNoSpecialControl = self._isBlocking and not self.hasValidNB() and not self.hasValid() and self._dataVoidOut is None
        netNodeToRtl = allocator.netNodeToRtl
        try:
            cur = netNodeToRtl[r_out]
            if hasNoSpecialControl:
                return cur
            else:
                return []  # because there are multiple outputs

        except KeyError:
            pass

        t = self.scheduledOut[0]

        dataRtl = self.getRtlDataSig()
        _data = TimeIndependentRtlResource(
            dataRtl,
            t,
            allocator, False)

        iea = self.netlist.allocator._iea
        hasManyArchElems = len(self.netlist.allocator._archElements) > 1
        netNodeToRtl[r_out] = _data
        for sync in self.dependsOn:
            if HdlType_isVoid(sync._dtype):
                continue
            assert isinstance(sync, HlsNetNodeOut), (self, self.dependsOn)
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only data path
            if hasManyArchElems and iea.ownerOfOutput[sync] is not allocator:
                continue
            sync.obj.allocateRtlInstance(allocator)

        _valid = None
        _validNB = None
        if self.hasValid() or self.hasValidNB():
            validRtl = self.getRtlValidSig(allocator)
            if self.hasValid():
                _valid = TimeIndependentRtlResource(
                    validRtl,
                    INVARIANT_TIME if isinstance(validRtl, HValue) else t,
                    allocator,
                    False)
                netNodeToRtl[self._valid] = _valid
            if self.hasValidNB():
                _validNB = TimeIndependentRtlResource(
                    validRtl,
                    INVARIANT_TIME if isinstance(validRtl, HValue) else t,
                    allocator,
                    False)
                netNodeToRtl[self._validNB] = _validNB
        if self._dataVoidOut is not None:
            self._allocateRtlInstanceDataVoidOut(allocator)

        if self._rawValue is not None:
            assert not self._isBlocking, self
            assert self.hasValid(), self
            if HdlType_isNonData(self._outputs[0]._dtype):
                if self.hasValidNB():
                    rawValue = Concat(validRtl, validRtl)
                    _rawValue = TimeIndependentRtlResource(
                        rawValue,
                        INVARIANT_TIME if isinstance(rawValue, HValue) else t,
                        allocator,
                        False)
                else:
                    _rawValue = _valid

            else:
                rawValue = Concat(validRtl, validRtl, dataRtl)
                _rawValue = TimeIndependentRtlResource(
                    rawValue,
                    INVARIANT_TIME if isinstance(rawValue, HValue) else t,
                    allocator,
                    False)
            netNodeToRtl[self._rawValue] = _rawValue

        # because there are multiple outputs
        return _data if hasNoSpecialControl else []

    def _getSchedulingResourceType(self):
        resourceType = self.src
        assert resourceType is not None, self
        return resourceType

    def checkScheduling(self):
        HlsNetNodeExplicitSync.checkScheduling(self)
        resourceType = self._getSchedulingResourceType()
        clkPeriod = self.netlist.normalizedClkPeriod
        clkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
        assert self.netlist.scheduler.resourceUsage[clkI].get(resourceType, None) is not None, (self, clkI, self.netlist.scheduler.resourceUsage)

    def resetScheduling(self):
        scheduledZero = self.scheduledZero
        if scheduledZero is None:
            return  # already restarted
        resourceType = self._getSchedulingResourceType()
        clkPeriod = self.netlist.normalizedClkPeriod
        self.netlist.scheduler.resourceUsage.removeUse(resourceType, indexOfClkPeriod(scheduledZero, clkPeriod))
        HlsNetNodeExplicitSync.resetScheduling(self)

    def setScheduling(self, schedule:SchedulizationDict):
        resourceUsage = self.netlist.scheduler.resourceUsage
        resourceType = self._getSchedulingResourceType()
        clkPeriod = self.netlist.normalizedClkPeriod

        if self.scheduledZero is not None:
            resourceUsage.removeUse(resourceType, indexOfClkPeriod(self.scheduledZero, clkPeriod))

        HlsNetNodeExplicitSync.setScheduling(self, schedule)
        self.netlist.scheduler.resourceUsage.addUse(resourceType, indexOfClkPeriod(self.scheduledZero, clkPeriod))

    def moveSchedulingTime(self, offset: int):
        clkPeriod = self.netlist.normalizedClkPeriod
        originalClkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
        HlsNetNode.moveSchedulingTime(self, offset)

        curClkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
        if originalClkI != curClkI:
            resourceType = self._getSchedulingResourceType()
            self.netlist.scheduler.resourceUsage.moveUse(resourceType, originalClkI, curClkI)

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]], beginOfFirstClk: int, outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        # schedule all dependencies
        if self.scheduledOut is None:
            HlsNetNode.scheduleAsap(self, pathForDebug, beginOfFirstClk, outputTimeGetter)
            scheduledZero = self.scheduledZero
            clkPeriod = self.netlist.normalizedClkPeriod
            curClkI = scheduledZero // clkPeriod
            resourceType = self._getSchedulingResourceType()
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

    def scheduleAlapCompaction(self, endOfLastClk: int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        originalTimeZero = self.scheduledZero
        netlist = self.netlist
        scheduler = netlist.scheduler
        clkPeriod = netlist.normalizedClkPeriod
        resourceType = self._getSchedulingResourceType()
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

    def getRtlDataSig(self):
        src: Interface = self.src

        if isinstance(src, HsStructIntf):
            return src.data._reinterpret_cast(Bits(src.data._dtype.bit_length()))

        if isinstance(src, Axi_hs):
            exclude = (src.valid, src.ready)

        elif isinstance(src, (Handshaked, HandshakeSync)):
            exclude = (src.vld, src.rd)

        elif isinstance(src, VldSynced):
            exclude = (src.vld,)

        elif isinstance(src, RdSynced):
            return packIntf(src,
                            masterDirEqTo=DIRECTION_opposite[INTF_DIRECTION_asDirecton[src.rd._direction]],
                            exclude=(src.rd,))
        else:
            return packIntf(src, masterDirEqTo=src._masterDir)

        assert exclude[0]._masterDir == DIRECTION.OUT, exclude[0]._masterDir
        return packIntf(src,
                        masterDirEqTo=exclude[0]._masterDir,
                        exclude=exclude)

    def _getInterfaceName(self, io: Union[Interface, Tuple[Interface]]) -> str:
        return getInterfaceName(self.netlist.parentUnit, io)

    def __repr__(self):
        return f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''} {self.src}>"


class HlsNetNodeReadIndexed(HlsNetNodeRead):
    """
    Same as :class:`~.HlsNetNodeRead` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src:Union[RtlSignal, Interface]):
        HlsNetNodeRead.__init__(self, netlist, src)
        self.indexes = [self._addInput("index0"), ]

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
                    indexesStrs.append(f"<{dep.obj._id}>.{dep.out_i}")
                else:
                    indexesStrs.append(repr(dep))

            return f"[{','.join(indexesStrs)}]"
        else:
            return ""

    def __repr__(self):
        return f"<{self.__class__.__name__:s}{'' if self._isBlocking else ' NB'} {self._id:d}{' ' + self.name if self.name else ''} {self.src}{self._strFormatIndexes(self.indexes)}>"
