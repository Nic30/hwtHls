from typing import Union, Optional, List, Generator

from hwt.code import Concat
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
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
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate, \
    HlsNetNodeAggregatePortOut, HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict, OutputTimeGetter, \
    OutputMinUseTimeGetter
from hwtHls.netlist.nodes.orderable import HOrderingVoidT
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    HlsNetNodeOutAny
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
    :ivar _valid: output with "valid" signal for non blocking reads which signalizes that the read was successful.
    :ivar _rawValue: Concat(valid, dataOut)
    """

    def __init__(self, netlist: "HlsNetlistCtx", src: Union[RtlSignal, Interface]):
        HlsNetNode.__init__(self, netlist, None)
        self.operator = "read"
        self.src = src
        self.maxIosPerClk = 1
        self._isBlocking = True
        self._valid = None
        self._rawValue = None
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None

        self._init_extraCond_skipWhen()
        self._addOutput(self.getRtlDataSig()._dtype, "dataOut")
        self._addOutput(HOrderingVoidT, "orderingOut")
    
    def setNonBlocking(self):
        self._isBlocking = False
        assert self._valid is None, (self, "Already is non blocking")
        self._rawValue = self._addOutput(Bits(self._outputs[0]._dtype.bit_length() + 1), "rawValue")
        self._valid = self._addOutput(BIT, "valid")
        
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        for i in self._inputs:
            if i not in (self.extraCond, self.skipWhen):
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

    def allocateRtlInstance(self, allocator: "ArchElement") -> Union[TimeIndependentRtlResource, List[HdlStatement]]:
        """
        Instantiate read operation on RTL level
        """
        r_out = self._outputs[0]
        try:
            cur = allocator.netNodeToRtl[r_out]
            if self._isBlocking:
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

        allocator.netNodeToRtl[r_out] = _data
        for sync in self.dependsOn:
            if sync._dtype == HOrderingVoidT:
                continue
            assert isinstance(sync, HlsNetNodeOut), (self, self.dependsOn)
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only data path
            sync.obj.allocateRtlInstance(allocator)
        
        if self._isBlocking:
            assert self._valid is None, self
        else:
            validRtl = self.getRtlValidSig(allocator)
            _valid = TimeIndependentRtlResource(
                validRtl,
                INVARIANT_TIME if isinstance(validRtl, HValue) else t,
                allocator,
                False)
            allocator.netNodeToRtl[self._valid] = _valid
            
            rawValue = Concat(validRtl, dataRtl)
            _rawValue = TimeIndependentRtlResource(
                rawValue,
                INVARIANT_TIME if isinstance(rawValue, HValue) else t,
                allocator,
                False)
            allocator.netNodeToRtl[self._rawValue] = _rawValue

        # because there are multiple outputs
        return _data if self._isBlocking else []

    def resetScheduling(self):
        scheduledZero = self.scheduledZero
        if scheduledZero is None:
            return  # already restarted
        HlsNetNodeExplicitSync.resetScheduling(self)
        resourceType = self.src if isinstance(self, HlsNetNodeRead) else self.dst
        clkPeriod = self.netlist.normalizedClkPeriod
        self.netlist.scheduler.resourceUsage.removeUse(resourceType, indexOfClkPeriod(scheduledZero, clkPeriod))

    def setScheduling(self, schedule:SchedulizationDict):
        resourceUsage = self.netlist.scheduler.resourceUsage
        resourceType = self.src if isinstance(self, HlsNetNodeRead) else self.dst
        clkPeriod = self.netlist.normalizedClkPeriod

        if self.scheduledZero is not None:
            resourceUsage.removeUse(resourceType, indexOfClkPeriod(self.scheduledZero, clkPeriod))

        HlsNetNodeExplicitSync.setScheduling(self, schedule)
        self.netlist.scheduler.resourceUsage.addUse(resourceType, indexOfClkPeriod(self.scheduledZero, clkPeriod))
    
    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]], beginOfFirstClk: int, outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        # schedule all dependencies
        if self.scheduledOut is None:
            HlsNetNode.scheduleAsap(self, pathForDebug, beginOfFirstClk, outputTimeGetter)
            scheduledZero = self.scheduledZero
            clkPeriod = self.netlist.normalizedClkPeriod
            curClkI = scheduledZero // clkPeriod
            resourceType = self.src if isinstance(self, HlsNetNodeRead) else self.dst
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
        scheduler = self.netlist.scheduler
        clkPeriod = self.netlist.normalizedClkPeriod
        resourceType = self.src if isinstance(self, HlsNetNodeRead) else self.dst

        originalClkI = indexOfClkPeriod(originalTimeZero, clkPeriod)
        tuple(HlsNetNodeExplicitSync.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter))
        curClkI = indexOfClkPeriod(self.scheduledZero, clkPeriod)
        if originalClkI != curClkI:
            scheduler.resourceUsage.moveUse(resourceType, originalClkI, curClkI)

        suitableClkI = scheduler.resourceUsage.findFirstClkISatisfyingLimitEndToStart(resourceType, curClkI, self.maxIosPerClk)
        if curClkI != suitableClkI:
            # move to next clock cycle if IO constraint requires it
            ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, scheduler.resolution)
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

    def __repr__(self):
        return f"<{self.__class__.__name__:s}{'' if self._valid is None else ' NB'} {self._id:d} {self.src}>"


class HlsNetNodeReadIndexed(HlsNetNodeRead):
    """
    Same as :class:`~.HlsNetNodeRead` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src:Union[RtlSignal, Interface]):
        HlsNetNodeRead.__init__(self, netlist, src)
        self.indexes = [self._addInput("index0"), ]

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        allNonOrdering = (self.extraCond, self.skipWhen, *self.indexes)
        for i in self._inputs:
            if i not in allNonOrdering:
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
        return f"<{self.__class__.__name__:s}{'' if self._valid is None else ' NB'} {self._id:d} {self.src}{self._strFormatIndexes(self.indexes)}>"
