from typing import Union, Optional, List

from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Signal, HandshakeSync, Handshaked, VldSynced, \
    RdSynced
from hwt.interfaces.structIntf import StructIntf
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import start_of_next_clk_period, start_clk, epsilon
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes, HlsNetNodeOutLazy, HlsNetNodeOutLazyIndirect
from hwtHls.netlist.utils import hls_op_and, hls_op_or
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.translation.toHwtHlsNetlist.opCache import SsaToHwtHlsNetlistOpCache
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi_intf_common import Axi_hs
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import packIntf

IO_COMB_REALIZATION = OpRealizationMeta(latency_post=epsilon)


class _HOrderingVoidT(HdlType):
    pass


HOrderingVoidT = _HOrderingVoidT()


class HlsNetNodeExplicitSync(HlsNetNode):
    """
    This node represents just wire in scheduled graph which has an extra synchronization conditions.
    :see: :class:`hwtLib.handshaked.streamNode.StreamNode`

    This node is used to stall/drop/not-require some data based on external conditions.

    :ivar extraCond: a flag which must be true to allow the transaction (is blocking until 1)
    :ivar extraCond_inI: index of extraCond input
    :ivar skipWhen: a flag which marks that this write should be skipped and transaction
                    will not be performed but the control flow will continue
    :ivar skipWhen_inI: index of skipWhen input
    """

    def __init__(self, parentHls: "HlsPipeline", dtype: HdlType):
        HlsNetNode.__init__(self, parentHls, None)
        self._init_extraCond_skipWhen()
        self._add_input()
        self._add_output(dtype)
        self._add_output(HOrderingVoidT)  # slot for ordering

    def _init_extraCond_skipWhen(self):
        self.extraCond: Optional[HlsNetNodeOut] = None
        self.extraCond_inI: Optional[int] = None
        self.skipWhen: Optional[HlsNetNodeOut] = None
        self.skipWhen_inI: Optional[int] = None

    def iterOrderingInputs(self):
        for i in self._inputs:
            if i.in_i != 0 and i.in_i != self.extraCond_inI and i.in_i != self.skipWhen_inI:
                yield i

    def allocateRtlInstance(self,
                          allocator: "AllocatorArchitecturalElement",
                          ) -> TimeIndependentRtlResource:
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

    def _unregisterLazyInput(self, cur: HlsNetNodeOutLazy, inI: int):
        found = False
        for i, dep in enumerate(cur.dependent_inputs):
            if isinstance(dep, HlsNetNodeOperatorPropertyInputRef) and\
                    dep.updated_obj is self and\
                    dep.in_i == inI:
                cur.dependent_inputs.pop(i)
                found = True
                break
        assert found, (self, cur.dependent_inputs)

    def add_control_extraCond(self, en: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        if self.extraCond is None:
            i = self._add_input()
            self.extraCond_inI = i.in_i

        else:
            # create "and" of existing and new extraCond and use it instead
            cur = self.extraCond
            if isinstance(cur, HlsNetNodeOutLazy):
                self._unregisterLazyInput(cur, self.extraCond_inI)

            en = hls_op_and(self.hls, self.extraCond, en)
            i = self._inputs[self.extraCond_inI]

        self.extraCond = en
        link_hls_nodes(en, i)
        if isinstance(en, HlsNetNodeOutLazy):
            en.dependent_inputs.append(HlsNetNodeOperatorPropertyInputRef(self, "extraCond", i.in_i, en))

    def add_control_skipWhen(self, skipWhen: Union[HlsNetNodeOut, HlsNetNodeOutLazy]):
        if self.skipWhen is None:
            self.skipWhen = skipWhen
            i = self._add_input()
            self.skipWhen_inI = i.in_i
        else:
            cur = self.skipWhen
            if isinstance(cur, HlsNetNodeOutLazy):
                self._unregisterLazyInput(cur, self.skipWhen_inI)

            skipWhen = hls_op_or(self.hls, cur, skipWhen)
            i = self._inputs[self.skipWhen_inI]

        link_hls_nodes(skipWhen, i)
        if isinstance(skipWhen, HlsNetNodeOutLazy):
            skipWhen.dependent_inputs.append(HlsNetNodeOperatorPropertyInputRef(self, "skipWhen", i.in_i, skipWhen))

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @classmethod
    def replace_variable(cls, parentHls: "HlsPipeline", cache_key,
                         var: Union[HlsNetNodeOut, HlsNetNodeOutLazy],
                         to_hls_cache: SsaToHwtHlsNetlistOpCache,
                         extraCond: HlsNetNodeOut,
                         skipWhen: HlsNetNodeOut):
        """
        Prepend the synchronization to an operation output representing variable.
        """
        self = cls(parentHls, var._dtype)
        parentHls.nodes.append(self)
        o = self._outputs[0]
        link_hls_nodes(var, self._inputs[0])
        assert to_hls_cache._to_hls_cache[cache_key] is var, (cache_key, to_hls_cache._to_hls_cache[cache_key], var)
        if isinstance(var, HlsNetNodeOutLazy):
            o = HlsNetNodeOutLazyIndirect(to_hls_cache, var, o)
        else:
            to_hls_cache._to_hls_cache[cache_key] = o

        self.add_control_extraCond(extraCond)
        self.add_control_skipWhen(skipWhen)

        return self, o

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} in={self.dependsOn[0]}, extraCond={self.extraCond}>"


class HlsNetNodeRead(HlsNetNodeExplicitSync, InterfaceBase):
    """
    Hls plane to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, parentHls: "HlsPipeline", src: Union[RtlSignal, Interface]):
        HlsNetNode.__init__(self, parentHls, None)
        self.operator = "read"
        self.src = src
        self.maxIosPerClk = 1

        self._init_extraCond_skipWhen()
        self._add_output(self.getRtlDataSig()._dtype)  # slot for data consummer
        self._add_output(HOrderingVoidT)  # slot for ordering

    def getOrderingOutPort(self):
        return self._outputs[1]

    def iterOrderingInputs(self):
        for i in self._inputs:
            if i.in_i != self.extraCond_inI and i.in_i != self.skipWhen_inI:
                yield i

    def allocateRtlInstance(self,
                          allocator: "AllocatorArchitecturalElement",
                          ) -> TimeIndependentRtlResource:
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
            assert isinstance(sync, HlsNetNodeOut), (self, self.dependsOn)
            # prepare sync inputs but do not connect it because we do not implement synchronization
            # in this step we are building only data path
            sync.obj.allocateRtlInstance(allocator)

        return _o

    def _getNumberOfIoInThisClkPeriod(self, intf: Interface, searchFromSrcToDst: bool):
        """
        Collect the total number of IO operations which may happen concurrently in this clock period.

        :note: This is not a total number of scheduled IO operations in this clock.
            It uses the information about if the operations may happen concurrently.
        """
        clkPeriod: int = self.hls.normalizedClkPeriod
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

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        HlsNetNodeExplicitSync.scheduleAlapCompaction(self, asapSchedule)
        curIoCnt = self._getNumberOfIoInThisClkPeriod(self.src if isinstance(self, HlsNetNodeRead) else self.dst, False)
        if curIoCnt > self.maxIosPerClk:
            # move to next clock cycle if IO constraint requires it
            ffdelay = self.hls.platform.get_ff_store_time(self.hls.realTimeClkPeriod, self.hls.scheduler.resolution)
            clkPeriod = self.hls.normalizedClkPeriod
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

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        # schedule all dependencies
        HlsNetNode.scheduleAsap(self, pathForDebug)
        curIoCnt = self._getNumberOfIoInThisClkPeriod(self.src if isinstance(self, HlsNetNodeRead) else self.dst, True)
        if curIoCnt > self.maxIosPerClk:
            # move to next clock cycle if IO constraint requires it
            off = start_of_next_clk_period(self.scheduledIn[0], self.hls.normalizedClkPeriod) - self.scheduledIn[0]
            self.scheduledIn = tuple(t + off for t in self.scheduledIn)
            self.scheduledOut = tuple(t + off for t in self.scheduledOut)

        return self.scheduledOut

    def getRtlDataSig(self):
        src = self.src
        if isinstance(src, HsStructIntf):
            return src.data
        elif isinstance(src, (Axi_hs)):
            return packIntf(src, exclude=(src.valid, src.ready))
        elif isinstance(src, (Handshaked, HandshakeSync)):
            return packIntf(src, exclude=(src.vld, src.rd))
        elif isinstance(src, VldSynced):
            return packIntf(src, exclude=(src.vld))
        elif isinstance(src, RdSynced):
            return packIntf(src, exclude=(src.rd))
        else:
            return src

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} {self.src}>"


class HlsNetNodeReadSync(HlsNetNode, InterfaceBase):
    """
    Hls plane to read a synchronization from an interface.
    e.g. signal valid for handshaked input, signal ready for handshaked output.

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, parentHls: "HlsPipeline"):
        HlsNetNode.__init__(self, parentHls, None)
        self._add_input()
        self._add_output(BIT)
        self.operator = "read_sync"

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self,
                          allocator: "AllocatorArchitecturalElement",
                          ) -> TimeIndependentRtlResource:
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
            self.getRtlControlEn(),
            t,
            allocator)
        allocator.netNodeToRtl[r_out] = _o
        return _o

    def getRtlControlEn(self):
        d = self.dependsOn[0]
        if isinstance(d.obj, HlsNetNodeRead):
            intf = d.obj.src
            if isinstance(intf, (Handshaked, HandshakeSync, VldSynced)):
                return intf.vld
            elif isinstance(intf, (Signal, RtlSignalBase, RdSynced)):
                return BIT.from_py(1)
            elif isinstance(intf, Axi_hs):
                return intf.valid
            else:
                raise NotImplementedError(intf)

        elif isinstance(d.obj, HlsNetNodeWrite):
            intf = d.obj.dst
            if isinstance(intf, (Handshaked, HandshakeSync, RdSynced)):
                return intf.rd
            elif isinstance(intf, (Signal, RtlSignalBase, VldSynced)):
                return BIT.from_py(1)
            elif isinstance(intf, Axi_hs):
                return intf.ready
            else:
                raise NotImplementedError(intf)

        else:
            raise NotImplementedError(d)

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"


class HlsNetNodeWrite(HlsNetNodeExplicitSync):
    """
    :ivar src: const value or HlsVariable
    :ivar dst: output interface not relatet to HLS

    :ivar dependsOn: list of dependencies for scheduling composed of data input, extraConds and skipWhen
    """

    def __init__(self, parentHls: "HlsPipeline", src, dst: Union[RtlSignal, Interface, SsaValue]):
        HlsNetNode.__init__(self, parentHls, None)
        self._init_extraCond_skipWhen()
        self._add_input()
        self._add_output(HOrderingVoidT)  # slot for ordering

        self.operator = "write"
        self.src = src

        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (Signal, RtlSignal)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp

        assert isinstance(dst, (HlsNetNodeIn, HsStructIntf, Signal, RtlSignalBase, Handshaked)), dst
        self.dst = dst

        self.indexes = indexCascade
        self.maxIosPerClk = 1

    def getOrderingOutPort(self):
        return self._outputs[0]

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        assert self.dependsOn, self
        return HlsNetNodeRead.scheduleAsap(self, pathForDebug)

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        return HlsNetNodeRead.scheduleAlapCompaction(self, asapSchedule)

    def _getNumberOfIoInThisClkPeriod(self, intf: Interface, searchFromSrcToDst: bool):
        return HlsNetNodeRead._getNumberOfIoInThisClkPeriod(self, intf, searchFromSrcToDst)

    def allocateRtlInstance(self,
                            allocator: "AllocatorArchitecturalElement",
                          ) -> List[HdlStatement]:
        """
        Instantiate write operation on RTL level
        """
        assert len(self.dependsOn) >= 1, self.dependsOn
        # [0] - data, [1:] control dependencies
        for sync, t in zip(self.dependsOn[1:], self.scheduledIn[1:]):
            # prepare sync intputs but do not connect it because we do not implement synchronization
            # in this step we are building only datapath
            if sync._dtype != HOrderingVoidT:
                allocator.instantiateHlsNetNodeOutInTime(sync, t)

        dep = self.dependsOn[0]
        _o = allocator.instantiateHlsNetNodeOutInTime(dep, self.scheduledIn[0])

        # apply indexes before assignments
        dst = self.dst
        _dst = dst
        if isinstance(dst, HsStructIntf):
            dst = dst.data

        if self.indexes is not None:
            for i in self.indexes:
                dst = dst[i]
        try:
            # skip instantiation of writes in the same mux
            return allocator.netNodeToRtl[(dep, dst)]
        except KeyError:
            pass

        if isinstance(dst, (Handshaked, Axi_hs)):
            if isinstance(_o.data, StructIntf):
                if isinstance(dst, Handshaked):
                    rd, vld = dst.rd, dst.vld
                else:
                    rd, vld = dst.ready, dst.valid
                rtlObj = dst(_o.data, exclude=(rd, vld))
            else:
                assert len(dst._interfaces) == 3, (dst, "Must have just ready,valid and data signal because the source is just a data signal", _o.data)
                rtlObj = dst.data(_o.data)
        else:
            rtlObj = dst(_o.data)
        # allocator.netNodeToRtl[o] = rtlObj
        allocator.netNodeToRtl[(dep, dst)] = rtlObj

        return rtlObj

    def __repr__(self):
        if self.indexes:
            indexes = "[%r]" % self.indexes
        else:
            indexes = ""

        return f"<{self.__class__.__name__:s} {self._id:d} {self.dst}{indexes:s} <- {self.src}>"


class HlsNetNodeOperatorPropertyInputRef():
    """
    An object which is used in HlsNetNodeOutLazy dependencies to update also HlsNetNodeRead/HlsNetNodeWrite object
    once the lazy output of some node on input is resolved.
    """

    def __init__(self, updated_obj: Union[HlsNetNodeRead, HlsNetNodeWrite], property_name:str, in_i:int, obj: HlsNetNodeOutLazy):
        self.updated_obj = updated_obj
        self.property_name = property_name
        self.in_i = in_i
        self.obj = obj
        self.replacedBy = None

    def replace_driver(self, new_obj: HlsNetNodeOut):
        assert self.replacedBy is None, self
        if isinstance(new_obj, HlsNetNodeOutLazy):
            assert self.obj is not new_obj, (self, new_obj)
            assert self not in new_obj.dependent_inputs, new_obj
            new_obj.dependent_inputs.append(self)
        else:
            assert isinstance(new_obj, HlsNetNodeOut), ("Must be a final out port", new_obj)
            usedBy = new_obj.obj.usedBy[new_obj.out_i]
            i = self.updated_obj._inputs[self.in_i]
            if i not in usedBy:
                usedBy.append(i)

        assert getattr(self.updated_obj, self.property_name) is self.obj, (getattr(self.updated_obj, self.property_name), self.obj)
        cur = self.updated_obj.dependsOn[self.in_i]
        assert cur is self.obj or cur is new_obj, (cur, self.obj, new_obj)
        setattr(self.updated_obj, self.property_name, new_obj)
        self.updated_obj.dependsOn[self.in_i] = new_obj
        self.replacedBy = new_obj
