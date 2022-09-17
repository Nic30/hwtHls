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
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict, InputTimeGetter, TimeSpec
from hwtHls.netlist.nodes.orderable import HOrderingVoidT
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    HlsNetNodeOutAny
from hwtHls.netlist.scheduler.clk_math import start_of_next_clk_period, start_clk
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

    def _getNumberOfIoInThisClkPeriod(self, intf: Interface, searchFromSrcToDst: bool) -> int:
        """
        Collect the total number of IO operations which may happen concurrently in this clock period.

        :note: This is not a total number of scheduled IO operations in this clock.
            It uses the information about if the operations may happen concurrently.
        """
        clkPeriod: int = self.netlist.normalizedClkPeriod
        if isinstance(self, HlsNetNodeRead):
            thisClkI = start_clk(self.scheduledOut[0], clkPeriod)
            sameIntf = intf is self.src
        else:
            thisClkI = start_clk(self.scheduledIn[0], clkPeriod)
            sameIntf = intf is self.dst

        ioCnt = 0
        if searchFromSrcToDst:
            for orderingIn in self.iterOrderingInputs():
                dep = self.dependsOn[orderingIn.in_i]
                assert isinstance(dep.obj, (HlsNetNodeExplicitSync, HlsNetNodeDelayClkTick)), ("ordering dependencies should be just between IO nodes and delays", orderingIn, dep, self)
                if start_clk(dep.obj.scheduledOut[dep.out_i], clkPeriod) == thisClkI:
                    ioCnt = max(ioCnt, dep.obj._getNumberOfIoInThisClkPeriod(intf, True))
        else:
            orderingOut = self.getOrderingOutPort()
            for dep in self.usedBy[orderingOut.out_i]:
                assert isinstance(dep.obj, (HlsNetNodeExplicitSync, HlsNetNodeDelayClkTick)), ("ordering dependencies should be just between IO nodes and delays", dep, self)
                if start_clk(dep.obj.scheduledIn[dep.in_i], clkPeriod) == thisClkI:
                    ioCnt = max(ioCnt, dep.obj._getNumberOfIoInThisClkPeriod(intf, False))

        if sameIntf:
            return ioCnt + 1
        else:
            return ioCnt

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        # schedule all dependencies
        HlsNetNode.scheduleAsap(self, pathForDebug)
        curIoCnt = self._getNumberOfIoInThisClkPeriod(self.src if isinstance(self, HlsNetNodeRead) else self.dst, True)
        if curIoCnt > self.maxIosPerClk:
            # move to next clock cycle if IO constraint requires it
            off = start_of_next_clk_period(self.scheduledIn[0], self.netlist.normalizedClkPeriod) - self.scheduledIn[0]
            self.scheduledIn = tuple(t + off for t in self.scheduledIn)
            self.scheduledOut = tuple(t + off for t in self.scheduledOut)

        return self.scheduledOut

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict, inputTimeGetter: Optional[InputTimeGetter]) -> TimeSpec:
        HlsNetNodeExplicitSync.scheduleAlapCompaction(self, asapSchedule, inputTimeGetter)
        curIoCnt = self._getNumberOfIoInThisClkPeriod(self.src if isinstance(self, HlsNetNodeRead) else self.dst, False)
        if curIoCnt > self.maxIosPerClk:
            # move to next clock cycle if IO constraint requires it
            ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
            clkPeriod = self.netlist.normalizedClkPeriod
            while curIoCnt > self.maxIosPerClk:
                if self.scheduledIn:
                    startT = self.scheduledIn[0]
                else:
                    startT = self.scheduledOut[0]

                off = start_of_next_clk_period(startT, clkPeriod) - startT - clkPeriod - ffdelay
                self.scheduledIn = tuple(t + off for t in self.scheduledIn)
                self.scheduledOut = tuple(t + off for t in self.scheduledOut)
                curIoCnt = self._getNumberOfIoInThisClkPeriod(self.src if isinstance(self, HlsNetNodeRead) else self.dst, False)

        return self.scheduledIn

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
