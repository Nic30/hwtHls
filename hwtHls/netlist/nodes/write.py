from typing import Union, Optional, List, Generator, Tuple

from hwt.hdl.statements.statement import HdlStatement
from hwt.interfaces.std import Signal, HandshakeSync, Handshaked, VldSynced, \
    RdSynced
from hwt.interfaces.structIntf import StructIntf
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import packIntf, \
    connectPacked
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode, OutputTimeGetter, \
    OutputMinUseTimeGetter, SchedulizationDict
from hwtHls.netlist.nodes.orderable import HVoidOrdering, HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    HlsNetNodeOutLazy
from hwtHls.netlist.nodes.read import HlsNetNodeRead, HlsNetNodeReadIndexed
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi_intf_common import Axi_hs


class HlsNetNodeWrite(HlsNetNodeExplicitSync):
    """
    :ivar src: const value or HlsVariable
    :ivar dst: output interface not related to HLS

    :ivar dependsOn: list of dependencies for scheduling composed of data input, extraConds and skipWhen
    """

    def __init__(self, netlist: "HlsNetlistCtx", src, dst: Union[RtlSignal, Interface, SsaValue]):
        HlsNetNode.__init__(self, netlist, None)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None

        self._initCommonPortProps()
        self._addInput("src")
        self.operator = "write"
        self.src = src
        assert not isinstance(src, (HlsNetNodeOut, HlsNetNodeOutLazy)), (src, "src is used for temporary states where node is not entirely constructed,"
                                                                         " the actual src is realized as _inputs[0]")

        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (Signal, RtlSignal)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp
        assert not indexCascade, ("There should not be any index, for indexed writes use :class:`~.HlsNetNodeWrite` node", src, dst, indexCascade)
        # assert isinstance(dst, (HlsNetNodeIn, HsStructIntf, Signal, RtlSignalBase, Handshaked, StructIntf, VldSynced, RdSynced)), dst
        self.dst = dst
        self.maxIosPerClk = 1
        self._isBlocking = True

    def resetScheduling(self):
        return HlsNetNodeRead.resetScheduling(self)

    def setScheduling(self, schedule:SchedulizationDict):
        return HlsNetNodeRead.setScheduling(self, schedule)

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]], beginOfFirstClk: int, outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        assert self.dependsOn, self
        return HlsNetNodeRead.scheduleAsap(self, pathForDebug, beginOfFirstClk, outputTimeGetter)

    def scheduleAlapCompaction(self, endOfLastClk:int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        return HlsNetNodeRead.scheduleAlapCompaction(self, endOfLastClk, outputMinUseTimeGetter)

    def allocateRtlInstance(self, allocator: "ArchElement") -> List[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert len(self.dependsOn) >= 1, self.dependsOn
        # [0] - data, [1:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if not HdlType_isVoid(sync._dtype):
                allocator.instantiateHlsNetNodeOutInTime(sync, t)

        dep = self.dependsOn[0]
        _o = allocator.instantiateHlsNetNodeOutInTime(dep, self.scheduledIn[0])

        # apply indexes before assignments
        dst = self.dst

        try:
            # skip instantiation of writes in the same mux
            return allocator.netNodeToRtl[(dep, dst)]
        except KeyError:
            pass

        if isinstance(dst, Axi_hs):
            exclude = dst.ready, dst.valid
        elif isinstance(dst, (Handshaked, HandshakeSync)):
            exclude = dst.rd, dst.vld
        elif isinstance(dst, VldSynced):
            exclude = (dst.vld,)
        elif isinstance(dst, RdSynced):
            exclude = (dst.rd,)
        else:
            exclude = ()

        if isinstance(_o.data, StructIntf):
            rtlObj = dst(_o.data, exclude=exclude)
        elif isinstance(_o.data, RtlSignal) and isinstance(dst, RtlSignal):
            rtlObj = dst(_o.data)
        elif isinstance(dst, RtlSignal):
            rtlObj = dst(packIntf(_o.data, exclude=exclude))
        else:
            rtlObj = connectPacked(_o.data, dst, exclude=exclude)

        # allocator.netNodeToRtl[o] = rtlObj
        allocator.netNodeToRtl[(dep, dst)] = rtlObj

        return rtlObj

    def _getInterfaceName(self, io: Union[Interface, Tuple[Interface]]) -> str:
        return HlsNetNodeRead._getInterfaceName(self, io)

    def __repr__(self, minify=False):
        src = self.src
        if src is NOT_SPECIFIED:
            src = self.dependsOn[0]
        dstName = "<None>" if self.dst is None else self._getInterfaceName(self.dst)
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {dstName}>"
        else:
            if src is None:
                _src = "<None>"
            else:
                _src = f"{src.obj._id}:{src.out_i}"
            return f"<{self.__class__.__name__:s} {self._id:d} {dstName} <- {_src:s}>"


class HlsNetNodeWriteIndexed(HlsNetNodeWrite):
    """
    Same as :class:`~.HlsNetNodeWrite` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src, dst:Union[RtlSignal, Interface, SsaValue]):
        HlsNetNodeWrite.__init__(self, netlist, src, dst)
        self.indexes = [self._addInput("index0"), ]

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
            return f"<{self.__class__.__name__:s} {self._id:d} {dstName}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {dstName}{HlsNetNodeReadIndexed._strFormatIndexes(self.indexes)} <- {src}>"
