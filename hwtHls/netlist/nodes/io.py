from typing import Union, Optional, List, Generator

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Signal, HandshakeSync, Handshaked, VldSynced, \
    RdSynced
from hwt.interfaces.structIntf import StructIntf
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import packIntf, \
    connectPacked
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict, TimeSpec
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes, HlsNetNodeOutLazy, HlsNetNodeOutAny
from hwtHls.netlist.scheduler.clk_math import start_of_next_clk_period, start_clk, epsilon
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi_intf_common import Axi_hs

IO_COMB_REALIZATION = OpRealizationMeta(outputWireDelay=epsilon)


class _HOrderingVoidT(HdlType):

    def bit_length(self):
        return 0


HOrderingVoidT = _HOrderingVoidT()


class HlsNetNodeExplicitSync(HlsNetNode):
    """
    This node represents just wire in scheduled graph which has an extra synchronization conditions.
    :see: :class:`hwtLib.handshaked.streamNode.StreamNode`

    This node is used to stall/drop/not-require some data based on external conditions.

    :ivar extraCond: an input for a flag which must be true to allow the transaction (is blocking until 1)
    :ivar skipWhen: an input for a flag which marks that this write should be skipped and transaction
                    will not be performed but the control flow will continue
    :ivar _associatedReadSync: a node which reads if this node is activated and working
    """

    def __init__(self, netlist: "HlsNetlistCtx", dtype: HdlType):
        HlsNetNode.__init__(self, netlist, name=None)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None
        self._init_extraCond_skipWhen()
        self._addInput("dataIn")
        self._addOutput(dtype, "dataOut")
        self._addOutput(HOrderingVoidT, "orderingOut")

    def _init_extraCond_skipWhen(self):
        self.extraCond: Optional[HlsNetNodeIn] = None
        self.skipWhen: Optional[HlsNetNodeIn] = None

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        for i in self._inputs:
            if i.in_i != 0 and i not in (self.extraCond, self.skipWhen):
                yield i

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        assert type(self) is HlsNetNodeExplicitSync, self
        op_out = self._outputs[0]

        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass
        # synchronization applied in allocator additionally, we just pass the data
        v = allocator.instantiateHlsNetNodeOut(self.dependsOn[0])
        allocator.netNodeToRtl[op_out] = v
        for conrol in self.dependsOn[1:]:
            conrol.obj.allocateRtlInstance(allocator)

        return v

    def add_control_extraCond(self, en: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        i = self.extraCond
        if i is None:
            self.extraCond = i = self._addInput("extraCond")
            link_hls_nodes(en, i)
        else:
            # create "and" of existing and new extraCond and use it instead
            cur = self.dependsOn[i.in_i]
            en = self.netlist.builder.buildAnd(cur, en)
            i.replaceDriver(en)

    def add_control_skipWhen(self, skipWhen: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        i = self.skipWhen
        if i is None:
            self.skipWhen = i = self._addInput("skipWhen")
            link_hls_nodes(skipWhen, i)
        else:
            cur = self.dependsOn[i.in_i]
            skipWhen = self.netlist.builder.buildOr(cur, skipWhen)
            i.replaceDriver(skipWhen)

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}"
        else:
            return (f"<{self.__class__.__name__:s} {self._id:d} in={self.dependsOn[0]}, "
                    f"extraCond={None if self.extraCond is None else self.dependsOn[self.extraCond.in_i]}, "
                    f"skipWhen={None if self.skipWhen is None else self.dependsOn[self.skipWhen.in_i]}>")


class HlsNetNodeRead(HlsNetNodeExplicitSync, InterfaceBase):
    """
    Hls plan to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, netlist: "HlsNetlistCtx", src: Union[RtlSignal, Interface]):
        HlsNetNode.__init__(self, netlist, None)
        self.operator = "read"
        self.src = src
        self.maxIosPerClk = 1
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None

        self._init_extraCond_skipWhen()
        self._addOutput(self.getRtlDataSig()._dtype, "dataOut")
        self._addOutput(HOrderingVoidT, "orderingOut")
            
    def getOrderingOutPort(self) -> HlsNetNodeOut:
        return self._outputs[1]

    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        for i in self._inputs:
            if i not in (self.extraCond, self.skipWhen):
                yield i

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        Instantiate read operation on RTL level
        """
        r_out = self._outputs[0]
        try:
            return allocator.netNodeToRtl[r_out]
        except KeyError:
            pass

        t = self.scheduledOut[0]
        _o = TimeIndependentRtlResource(
            self.getRtlDataSig(),
            t,
            allocator)

        allocator.netNodeToRtl[r_out] = _o
        for sync in self.dependsOn:
            if sync._dtype == HOrderingVoidT:
                continue
            assert isinstance(sync, HlsNetNodeOut), (self, self.dependsOn)
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only data path
            sync.obj.allocateRtlInstance(allocator)

        return _o

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
                assert isinstance(dep.obj, HlsNetNodeExplicitSync), ("ordering dependencies should be just between IO nodes", dep, self)
                if start_clk(dep.obj.scheduledOut[dep.out_i], clkPeriod) == thisClkI:
                    ioCnt = max(ioCnt, dep.obj._getNumberOfIoInThisClkPeriod(intf, True))
        else:
            orderingOut = self.getOrderingOutPort()
            for dep in self.usedBy[orderingOut.out_i]:
                assert isinstance(dep.obj, HlsNetNodeExplicitSync), ("ordering dependencies should be just between IO nodes", dep, self)
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

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict) -> TimeSpec:
        HlsNetNodeExplicitSync.scheduleAlapCompaction(self, asapSchedule)
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
        elif isinstance(src, (Axi_hs)):
            return packIntf(src, masterDirEqTo=src._masterDir, exclude=(src.valid, src.ready))
        elif isinstance(src, (Handshaked, HandshakeSync)):
            return packIntf(src, masterDirEqTo=src._masterDir, exclude=(src.vld, src.rd))
        elif isinstance(src, VldSynced):
            return packIntf(src, masterDirEqTo=src._masterDir, exclude=(src.vld,))
        elif isinstance(src, RdSynced):
            return packIntf(src, masterDirEqTo=src._masterDir, exclude=(src.rd,))
        else:
            return packIntf(src, masterDirEqTo=src._masterDir)

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} {self.src}>"


class HlsNetNodeReadIndexed(HlsNetNodeRead):
    """
    Same as :class:`~.HlsNetNodeRead` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src:Union[RtlSignal, Interface]):
        HlsNetNodeRead.__init__(self, netlist, src)
        self.indexes = [self._addInput("index0"), ]
    
    @staticmethod
    def _strFormatIndexes(indexes: List[HlsNetNodeIn]):
        if indexes:
            indexesStrs = []
            for i in indexes:
                i: HlsNetNodeIn
                dep: Optional[HlsNetNodeOutAny] = i.obj.dependsOn[i.in_i]
                if isinstance(dep, HlsNetNodeOut):
                    indexesStrs.append(f"{dep.obj._id}.{dep.out_i}")
                else:
                    indexesStrs.append(repr(dep))

            indexes = f"[{','.join(indexesStrs)}]"
        else:
            indexes = ""

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} {self.src}{self._strFormatIndexes(self.indexes)}>"


class HlsNetNodeWrite(HlsNetNodeExplicitSync):
    """
    :ivar src: const value or HlsVariable
    :ivar dst: output interface not related to HLS

    :ivar dependsOn: list of dependencies for scheduling composed of data input, extraConds and skipWhen
    """

    def __init__(self, netlist: "HlsNetlistCtx", src, dst: Union[RtlSignal, Interface, SsaValue], addOrderingOut=True):
        HlsNetNode.__init__(self, netlist, None)
        self._associatedReadSync: Optional["HlsNetNodeReadSync"] = None

        self._init_extraCond_skipWhen()
        self._addInput("src")
        if addOrderingOut:
            self._addOutput(HOrderingVoidT, "orderingOut")  # slot for ordering

        self.operator = "write"
        self.src = src
        assert not isinstance(src, (HlsNetNodeOut, HlsNetNodeOutLazy)), src

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

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        return self._outputs[0]

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        assert self.dependsOn, self
        return HlsNetNodeRead.scheduleAsap(self, pathForDebug)

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        return HlsNetNodeRead.scheduleAlapCompaction(self, asapSchedule)

    def _getNumberOfIoInThisClkPeriod(self, intf: Interface, searchFromSrcToDst: bool):
        return HlsNetNodeRead._getNumberOfIoInThisClkPeriod(self, intf, searchFromSrcToDst)

    def allocateRtlInstance(self,
                            allocator: "ArchElement",
                          ) -> List[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert len(self.dependsOn) >= 1, self.dependsOn
        # [0] - data, [1:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if sync._dtype != HOrderingVoidT:
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
        else:
            rtlObj = connectPacked(_o.data, dst, exclude=exclude)

        # allocator.netNodeToRtl[o] = rtlObj
        allocator.netNodeToRtl[(dep, dst)] = rtlObj

        return rtlObj

    def __repr__(self):
        src = self.src
        if src is NOT_SPECIFIED:
            src = self.dependsOn[0]

        return f"<{self.__class__.__name__:s} {self._id:d} {self.dst} <- {src}>"


class HlsNetNodeWriteIndexed(HlsNetNodeWrite):
    """
    Same as :class:`~.HlsNetNodeWrite` but for memory mapped interfaces with address or index.
    """

    def __init__(self, netlist:"HlsNetlistCtx", src, dst:Union[RtlSignal, Interface, SsaValue], addOrderingOut=True):
        HlsNetNodeWrite.__init__(self, netlist, src, dst, addOrderingOut=addOrderingOut)
        self.indexes = [self._addInput("index0"), ]
        
    def __repr__(self):
        src = self.src
        if src is NOT_SPECIFIED:
            src = self.dependsOn[0]

        return f"<{self.__class__.__name__:s} {self._id:d} {self.dst}{HlsNetNodeReadIndexed._strFormatIndexes(self.indexes)} <- {src}>"
