from typing import List, Union, Optional

from hwt.doc_markers import internal
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Signal
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResourceItem, \
    TimeIndependentRtlResource
from hwtHls.clk_math import epsilon
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.opCache import SsaToHwtHlsNetlistOpCache
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.netlist.nodes.ports import HlsOperationIn, HlsOperationOut, \
    link_hls_nodes, HlsOperationOutLazy, HlsOperationOutLazyIndirect
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.tmpVariable import HlsTmpVariable
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase


IO_COMB_REALIZATION = OpRealizationMeta(latency_post=epsilon)


class HlsExplicitSyncNode(AbstractHlsOp):
    """
    This node represents just wire in scheduled graph which has an extra synchronization conditions.
    :see: :class:`hwtLib.handshaked.streamNode.StreamNode`

    This node is used to stall/drop/not-require some data based on external conditions.

    :ivar extraCond: a flag which must be true to allow the transaction (is blocking until 1)
    # :ivar skipWhen: a flag which marks that this write should be skipped and transaction
    #                 will not be performed but the control flow will continue
    """

    def __init__(self, parentHls: "HlsPipeline"):
        AbstractHlsOp.__init__(self, parentHls, None)
        self.extraCond: Optional[HlsOperationOut] = None
        # self.skipWhen: Optional[HlsOperationOut] = None
        self._add_input()
        self._add_output()

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

    def add_control_extraCond(self, en: Union[HlsOperationOut, HlsOperationOutLazy]):
        assert self.extraCond is None, ("Must be added only once")
        self.extraCond = en
        i = self._add_input()
        link_hls_nodes(en, i)
        if isinstance(en, HlsOperationOutLazy):
            en.dependent_inputs.append(HlsOperationPropertyInputRef(self, "extraCond", i.in_i, en))

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    # def add_control_skipWhen(self, skipWhen: Union[HlsOperationOut, HlsOperationOutLazy]):
    #    assert self.skipWhen is None, ("Must be added only once")
    #    self.skipWhen = skipWhen
    #    i = self._add_input()
    #    link_hls_nodes(skipWhen, i)
    #    if isinstance(skipWhen, HlsOperationOutLazy):
    #        skipWhen.dependent_inputs.append(HlsOperationPropertyInputRef(self, "skipWhen", i.in_i, skipWhen))

    @classmethod
    def replace_variable(cls, parentHls: "HlsPipeline", cache_key,
                         var: Union[HlsOperationOut, HlsOperationOutLazy],
                         to_hls_cache: SsaToHwtHlsNetlistOpCache,
                         en: HlsOperationOut):
        """
        Prepend the synchronization to an operation output representing variable.
        """
        self = cls(parentHls)
        o = self._outputs[0]
        link_hls_nodes(var, self._inputs[0])
        assert to_hls_cache._to_hls_cache[cache_key] is var, (cache_key, to_hls_cache._to_hls_cache[cache_key], var)
        if isinstance(var, HlsOperationOutLazy):
            o = HlsOperationOutLazyIndirect(to_hls_cache, var, o)
        else:
            to_hls_cache._to_hls_cache[cache_key] = o

        self.add_control_extraCond(en)

        return self, o

    def __repr__(self):
        return f"<{self.__class__.__name__:s} in={self.dependsOn[0]}, extraCond={self.extraCond}>"


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
        self.extraCond: Optional[HlsOperationOut] = None
        self._add_output()  # slot for data consummer

        self.operator = "read"

        # if isinstance(src, RtlSignalBase):
        #    self._inputs.append(src)
        # elif isinstance(src, Signal):
        #    self._inputs.append(src._sig)
        # else:
        #    assert isinstance(src, (HsStructIntf, HandshakeSync)), src
        #    if isinstance(src, HsStructIntf):
        #        for s in walkPhysInterfaces(src.data):
        #            self._inputs.append(s._sig)

        # t = dataSig._dtype
        # instantiate signal for value from this read
        # self._sig = parentHls.ctx.sig(
        #    "hsl_" + getSignalName(src),
        #    dtype=t)
        # self._sig.hidden =  False
        #
        # self._sig.origin = self
        # self._sig.drivers.append(self)
        self.src = src

        # parentHls.inputs.append(self)

    def add_control_extraCond(self, en: Union[HlsOperationOut, HlsOperationOutLazy]):
        HlsExplicitSyncNode.add_control_extraCond(self, en)

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
            self.scheduledInEnd[0],
            allocator)
        allocator._registerSignal(r_out, _o, used_signals)
        for sync in self.dependsOn:
            assert isinstance(sync, HlsOperationOut), (self, self.dependsOn)
            # prepare sync intputs but do not connect it because we do not implemet synchronization
            # in this step we are building only datapath
            allocator.instantiateHlsOperationOut(sync, used_signals)
        return _o

    # def add_control_skipWhen(self, skipWhen: Union[HlsOperationOut, HlsOperationOutLazy]):
    #    HlsExplicitSyncNode.add_control_skipWhen(self, skipWhen)

    def getRtlDataSig(self):
        src = self.src
        if isinstance(src, HsStructIntf):
            return src.data
        else:
            return src

    @internal
    def _destroy(self):
        self.hls.inputs.remove(self)

    def __repr__(self):
        return f"<{self.__class__.__name__:s}, {self.src}>"


class HlsWrite(HlsExplicitSyncNode):
    """
    :ivar src: const value or HlsVariable
    :ivar dst: output interface not relatet to HLS

    :ivar dependsOn: list of dependencies for scheduling composed of data input, extraConds and skipWhen
    """

    def __init__(self, parentHls: "HlsPipeline", src, dst: Union[RtlSignal, Interface, HlsTmpVariable]):
        AbstractHlsOp.__init__(self, parentHls, None)
        self.extraCond: Optional[HlsOperationOut] = None
        self._add_input()
        self.operator = "write"
        self.src = src
        if isinstance(src, RtlSignal):
            src.endpoints.append(self)

        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (Signal, RtlSignal)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp

        self.dst = dst
        # parentHls.outputs.append(self)
        if isinstance(dst, RtlSignal):
            pass
        else:
            assert isinstance(dst, (HlsOperationIn, HsStructIntf, Signal, RtlSignalBase)), dst

        self.indexes = indexCascade

    def add_control_extraCond(self, en: Union[HlsOperationOut, HlsOperationOutLazy]):
        HlsExplicitSyncNode.add_control_extraCond(self, en)

    # def add_control_skipWhen(self, skipWhen: Union[HlsOperationOut, HlsOperationOutLazy]):
    #     HlsExplicitSyncNode.add_control_skipWhen(self, skipWhen)
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
        # translate HlsIo object to signal
        dst = allocator.parentHls._io.get(dst, dst)
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

        _o = _o.get(dep.obj.scheduledInEnd[0])

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

        return f"<{self.__class__.__name__:s}, {self.dst}{indexes:s} <- {self.src}>"


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

    def replace_driver(self, new_obj: HlsOperationOut):
        if isinstance(new_obj, HlsOperationOutLazy):
            assert self.obj is not new_obj, (self, new_obj)
            assert self not in new_obj.dependent_inputs, new_obj
            new_obj.dependent_inputs.append(self)
        else:
            assert isinstance(new_obj, HlsOperationOut), ("Must be a final out port", new_obj)

        assert getattr(self.updated_obj, self.property_name) == self.obj, (getattr(self.updated_obj, self.property_name), self.obj)
        assert self.updated_obj.dependsOn[self.in_i] == self.obj, (self.updated_obj.dependsOn[self.in_i], self.obj)
        setattr(self.updated_obj, self.property_name, new_obj)
        self.updated_obj.dependsOn[self.in_i] = new_obj
