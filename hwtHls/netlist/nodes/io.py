from typing import Union, Optional, List

from hwt.doc_markers import internal
from hwt.hdl.types.defs import BIT
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Signal, HandshakeSync, Handshaked, VldSynced, \
    RdSynced
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResourceItem, \
    TimeIndependentRtlResource
from hwtHls.clk_math import epsilon, start_of_next_clk_period, start_clk
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.netlist.nodes.ports import HlsOperationIn, HlsOperationOut, \
    link_hls_nodes, HlsOperationOutLazy, HlsOperationOutLazyIndirect
from hwtHls.netlist.utils import hls_op_and, hls_op_or
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.ssa.translation.toHwtHlsNetlist.opCache import SsaToHwtHlsNetlistOpCache
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo

IO_COMB_REALIZATION = OpRealizationMeta(latency_post=epsilon)


class HlsExplicitSyncNode(AbstractHlsOp):
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

    def __init__(self, parentHls: "HlsPipeline"):
        AbstractHlsOp.__init__(self, parentHls, None)
        self._init_extraCond_skipWhen()
        self._add_input()
        self._add_output()

    def _init_extraCond_skipWhen(self):
        self.extraCond: Optional[HlsOperationOut] = None
        self.extraCond_inI: Optional[int] = None
        self.skipWhen: Optional[HlsOperationOut] = None
        self.skipWhen_inI: Optional[int] = None

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        assert type(self) is HlsExplicitSyncNode, self
        op_out = self._outputs[0]

        try:
            return allocator.node2instance[op_out]
        except KeyError:
            pass
        # synchronization applied in allocator additionally, we just pass the data
        v = allocator.instantiateHlsOperationOut(self.dependsOn[0], used_signals)
        allocator._registerSignal(op_out, v, used_signals)
        for conrol in self.dependsOn[1:]:
            allocator.instantiateHlsOperationOut(conrol, used_signals)
        return v

    def _unregisterLazyInput(self, cur: HlsOperationOutLazy, inI: int):
        found = False
        for i, dep in enumerate(cur.dependent_inputs):
            if isinstance(dep, HlsOperationPropertyInputRef) and\
                    dep.updated_obj is self and\
                    dep.in_i == inI:
                cur.dependent_inputs.pop(i)
                found = True
                break
        assert found, (self, cur.dependent_inputs)

    def add_control_extraCond(self, en: Union[HlsOperationOut, HlsOperationOutLazy]):
        if self.extraCond is None:
            i = self._add_input()
            self.extraCond_inI = i.in_i

        else:
            # create "and" of existing and new extraCond and use it instead
            cur = self.extraCond
            if isinstance(cur, HlsOperationOutLazy):
                self._unregisterLazyInput(cur, self.extraCond_inI)

            en = hls_op_and(self.hls, self.extraCond, en)
            i = self._inputs[self.extraCond_inI]

        self.extraCond = en
        link_hls_nodes(en, i)
        if isinstance(en, HlsOperationOutLazy):
            en.dependent_inputs.append(HlsOperationPropertyInputRef(self, "extraCond", i.in_i, en))

    def add_control_skipWhen(self, skipWhen: Union[HlsOperationOut, HlsOperationOutLazy]):
        if self.skipWhen is None:
            self.skipWhen = skipWhen
            i = self._add_input()
            self.skipWhen_inI = i.in_i
        else:
            cur = self.skipWhen
            if isinstance(cur, HlsOperationOutLazy):
                self._unregisterLazyInput(cur, self.skipWhen_inI)

            skipWhen = hls_op_or(self.hls, cur, skipWhen)
            i = self._inputs[self.skipWhen_inI]

        link_hls_nodes(skipWhen, i)
        if isinstance(skipWhen, HlsOperationOutLazy):
            skipWhen.dependent_inputs.append(HlsOperationPropertyInputRef(self, "skipWhen", i.in_i, skipWhen))

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @classmethod
    def replace_variable(cls, parentHls: "HlsPipeline", cache_key,
                         var: Union[HlsOperationOut, HlsOperationOutLazy],
                         to_hls_cache: SsaToHwtHlsNetlistOpCache,
                         extraCond: HlsOperationOut,
                         skipWhen: HlsOperationOut):
        """
        Prepend the synchronization to an operation output representing variable.
        """
        self = cls(parentHls)
        parentHls.nodes.append(self)
        o = self._outputs[0]
        link_hls_nodes(var, self._inputs[0])
        assert to_hls_cache._to_hls_cache[cache_key] is var, (cache_key, to_hls_cache._to_hls_cache[cache_key], var)
        if isinstance(var, HlsOperationOutLazy):
            o = HlsOperationOutLazyIndirect(to_hls_cache, var, o)
        else:
            to_hls_cache._to_hls_cache[cache_key] = o

        self.add_control_extraCond(extraCond)
        self.add_control_skipWhen(skipWhen)

        return self, o

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} in={self.dependsOn[0]}, extraCond={self.extraCond}>"


class HlsRead(HlsExplicitSyncNode, InterfaceBase):
    """
    Hls plane to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, parentHls: "HlsPipeline",
                 src: Union[RtlSignal, Interface]):
        AbstractHlsOp.__init__(self, parentHls, None)
        self._init_extraCond_skipWhen()
        self._add_output()  # slot for data consummer

        self.operator = "read"
        self.src = src
        self.maxIosPerClk = 1

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        """
        Instantiate read operation on RTL level
        """
        r_out = self._outputs[0]
        try:
            return allocator.node2instance[r_out]
        except KeyError:
            pass

        _o = TimeIndependentRtlResource(
            self.getRtlDataSig(),
            self.scheduledOut[0],
            allocator)
        allocator._registerSignal(r_out, _o, used_signals)
        for sync in self.dependsOn:
            assert isinstance(sync, HlsOperationOut), (self, self.dependsOn)
            # prepare sync intputs but do not connect it because we do not implemet synchronization
            # in this step we are building only datapath
            allocator.instantiateHlsOperationOut(sync, used_signals)

        return _o

    def scheduleAsap(self, clk_period: float, pathForDebug: Optional[UniqList["AbstractHlsOp"]]) -> List[float]:
        AbstractHlsOp.scheduleAsap(self, clk_period, pathForDebug)
        otherIoOps = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverIo).io_by_interface[self.src]

        while True:
            curClk = start_clk(self.asap_start[0], clk_period)
            iosInThisClk = 0
            for io in otherIoOps:
                end = io.asap_end
                if end is not None:
                    c = start_clk(io.asap_start[0], clk_period)
                    if c == curClk:
                        iosInThisClk += 1
    
            if iosInThisClk > self.maxIosPerClk:
                # move to next clock cycle
                off = start_of_next_clk_period(self.asap_start[0], clk_period) - self.asap_start[0]
                self.asap_start = tuple(t + off for t in self.asap_start)
                self.asap_end = tuple(t + off for t in self.asap_end)
            else:
                break
            
        return self.asap_end

    def getRtlDataSig(self):
        src = self.src
        if isinstance(src, (HsStructIntf, Handshaked, HandshakeSync, VldSynced, RdSynced)):
            return src.data
        else:
            return src

    @internal
    def _destroy(self):
        self.hls.inputs.remove(self)

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} {self.src}>"


class HlsReadSync(AbstractHlsOp, InterfaceBase):
    """
    Hls plane to read a synchronization from an interface.
    e.g. signal valid for handshaked input, signal ready for handshaked output.

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, parentHls: "HlsPipeline"):
        AbstractHlsOp.__init__(self, parentHls, None)
        self._add_input()
        self._add_output()
        self.operator = "read_sync"

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        """
        Instantiate read operation on RTL level
        """
        r_out = self._outputs[0]
        try:
            return allocator.node2instance[r_out]
        except KeyError:
            pass

        _o = TimeIndependentRtlResource(
            self.getRtlControlEn(),
            self.scheduledOut[0],
            allocator)
        allocator._registerSignal(r_out, _o, used_signals)

        # for sync in self.dependsOn:
        #    assert isinstance(sync, HlsOperationOut), (self, self.dependsOn)
        #    # prepare sync intputs but do not connect it because we do not implemet synchronization
        #    # in this step we are building only datapath
        #    allocator.instantiateHlsOperationOut(sync, used_signals)
        return _o

    def getRtlControlEn(self):
        d = self.dependsOn[0]
        if isinstance(d.obj, HlsRead):
            intf = d.obj.src
            if isinstance(intf, (Handshaked, HandshakeSync, VldSynced)):
                return intf.vld
            elif isinstance(intf, (Signal, RtlSignalBase, RdSynced)):
                return BIT.from_py(1)
            elif isinstance(intf, AxiStream):
                return intf.valid
            else:
                raise NotImplementedError(intf)

        elif isinstance(d.obj, HlsWrite):
            intf = d.obj.dst
            if isinstance(intf, (Handshaked, HandshakeSync, RdSynced)):
                return intf.rd
            elif isinstance(intf, (Signal, RtlSignalBase, VldSynced)):
                return BIT.from_py(1)
            elif isinstance(intf, AxiStream):
                return intf.ready
            else:
                raise NotImplementedError(intf)

        else:
            raise NotImplementedError(d)

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"


class HlsWrite(HlsExplicitSyncNode):
    """
    :ivar src: const value or HlsVariable
    :ivar dst: output interface not relatet to HLS

    :ivar dependsOn: list of dependencies for scheduling composed of data input, extraConds and skipWhen
    """

    def __init__(self, parentHls: "HlsPipeline", src, dst: Union[RtlSignal, Interface, SsaValue]):
        AbstractHlsOp.__init__(self, parentHls, None)
        self._init_extraCond_skipWhen()
        self._add_input()
        self.operator = "write"
        self.src = src

        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (Signal, RtlSignal)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp

        assert isinstance(dst, (HlsOperationIn, HsStructIntf, Signal, RtlSignalBase)), dst
        self.dst = dst

        self.indexes = indexCascade
        self.maxIosPerClk = 1

    def scheduleAsap(self, clk_period: float, pathForDebug: Optional[UniqList["AbstractHlsOp"]]) -> List[float]:
        # [todo] duplicit code with HlsRead
        # [todo] mv to scheduler as the generic resource constraint
        assert self.dependsOn, self
        AbstractHlsOp.scheduleAsap(self, clk_period, pathForDebug)
        otherIoOps = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverIo).io_by_interface[self.dst]

        while True:
            curClk = start_clk(self.asap_start[0], clk_period)
            iosInThisClk = 0
            for io in otherIoOps:
                end = io.asap_end
                if end is not None:
                    c = start_clk(io.asap_start[0], clk_period)
                    if c == curClk:
                        iosInThisClk += 1
    
            if iosInThisClk > self.maxIosPerClk:
                # move to next clock cycle
                off = start_of_next_clk_period(self.asap_start[0], clk_period) - self.asap_start[0]
                self.asap_start = tuple(t + off for t in self.asap_start)
                self.asap_end = tuple(t + off for t in self.asap_end)
            else:
                break
            
        return self.asap_end
        
    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        """
        Instantiate write operation on RTL level
        """
        assert len(self.dependsOn) >= 1, self.dependsOn
        # [0] - data, [1:] control dependencies
        for sync in self.dependsOn[1:]:
            # prepare sync intputs but do not connect it because we do not implemet synchronization
            # in this step we are building only datapath
            allocator.instantiateHlsOperationOut(sync, used_signals)

        dep = self.dependsOn[0]
        _o = allocator.instantiateHlsOperationOut(dep, used_signals)

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
            return allocator.node2instance[(dep, dst)]
        except KeyError:
            pass

        _o = _o.get(dep.obj.scheduledOut[0])

        rtlObj = dst(_o.data)
        # allocator.node2instance[o] = rtlObj
        allocator.node2instance[(dep, dst)] = rtlObj

        return rtlObj

    @internal
    def _destroy(self):
        self.hls.outputs.remove(self)

    def __repr__(self):
        if self.indexes:
            indexes = "[%r]" % self.indexes
        else:
            indexes = ""

        return f"<{self.__class__.__name__:s} {self._id:d} {self.dst}{indexes:s} <- {self.src}>"


class HlsOperationPropertyInputRef():
    """
    An object which is used in HlsOperationOutLazy dependencies to update also HlsRead/HlsWrite object
    once the lazy output of some node on input is resolved.
    """

    def __init__(self, updated_obj: Union[HlsRead, HlsWrite], property_name:str, in_i:int, obj: HlsOperationOutLazy):
        self.updated_obj = updated_obj
        self.property_name = property_name
        self.in_i = in_i
        self.obj = obj
        self.replacedBy = None

    def replace_driver(self, new_obj: HlsOperationOut):
        assert self.replacedBy is None, self
        if isinstance(new_obj, HlsOperationOutLazy):
            assert self.obj is not new_obj, (self, new_obj)
            assert self not in new_obj.dependent_inputs, new_obj
            new_obj.dependent_inputs.append(self)
        else:
            assert isinstance(new_obj, HlsOperationOut), ("Must be a final out port", new_obj)

        assert getattr(self.updated_obj, self.property_name) is self.obj, (getattr(self.updated_obj, self.property_name), self.obj)
        cur = self.updated_obj.dependsOn[self.in_i]
        assert cur is self.obj or cur is new_obj, (cur, self.obj, new_obj)
        setattr(self.updated_obj, self.property_name, new_obj)
        self.updated_obj.dependsOn[self.in_i] = new_obj
        self.replacedBy = new_obj
