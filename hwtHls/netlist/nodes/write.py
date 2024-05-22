from typing import Union, Optional, List, Generator, Tuple

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.struct import HStruct
from hwt.hdl.const import HConst
from hwt.hwIOs.std import HwIOSignal
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.pyUtils.setList import SetList
from hwt.hwIO import HwIO
from hwt.synthesizer.interfaceLevel.utils import HwIO_pack, \
    HwIO_connectPacked
from hwt.constants import NOT_SPECIFIED
from hwt.mainBases import RtlSignalBase
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
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.ssa.value import SsaValue
from hwt.pyUtils.typingFuture import override
from hwtLib.handshaked.streamNode import HwIOOrValidReadyTuple


class HlsNetNodeWrite(HlsNetNodeExplicitSync):
    """
    :ivar dst: output interface not related to HLS

    :ivar dependsOn: list of dependencies for scheduling composed of data input, extraConds and skipWhen
    """

    def __init__(self, netlist: "HlsNetlistCtx", dst: Union[RtlSignal, HwIO, SsaValue, None], name:Optional[str]=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self._initCommonPortProps(dst)
        self._addInput("src")
        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (HwIOSignal, RtlSignal)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp
        assert not indexCascade, ("There should not be any dst index, for indexed writes use :class:`~.HlsNetNodeWrite` node", dst, indexCascade)
        # assert isinstance(dst, (HlsNetNodeIn, HwIOStructRdVld, HwIOSignal, RtlSignalBase, HwIODataRdVld, HwIOStruct, HwIODataVld, HwIODataRd)), dst
        self.dst = dst
        self.maxIosPerClk = 1
        self._isBlocking = True
        self._mayBecomeFlushable = True
        self._isFlushable = False

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

    @override
    def getAllocatedRTL(self, allocator: "ArchElement"):
        assert self._isRtlAllocated, self
        dst = self.dst
        dep = self.dependsOn[0]
        return allocator.netNodeToRtl[(dep, dst)]

    def getRtlReadySig(self, hwIO: HwIOOrValidReadyTuple) -> Union[RtlSignalBase, HConst]:
        rd = HwIO_getSyncTuple(hwIO)[1]
        if isinstance(rd, int):
            raise NotImplementedError("rtl ready should not be requested because it is constant", self)
        else:
            return rd

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> List[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert not self._isRtlAllocated, self
        assert len(self.dependsOn) >= 1, (self, self.dependsOn)
        if self._isFlushable:
            raise NotImplementedError()

        # apply indexes before assignments
        dst = self.dst
        dep = self.dependsOn[0]
        assert dep is not None, self

        # [0] - data, [1:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if not HdlType_isVoid(sync._dtype):
                allocator.rtlAllocHlsNetNodeOutInTime(sync, t)

        if self.hasValid() or self.hasValidNB():
            raise AssertionError("Valid of write is always 1 and this port should be already optimized out")

        if self.hasAnyUsedReadyPort():
            readyRtl = self.getRtlReadySig(self.dst)
            if self.hasReady():
                allocator.rtlRegisterOutputRtlSignal(self._ready, readyRtl, False, False, True)
            if self.hasReadyNB():
                allocator.rtlRegisterOutputRtlSignal(self._readyNB, readyRtl, False, False, True)

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
