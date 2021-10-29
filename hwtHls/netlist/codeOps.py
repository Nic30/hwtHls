from copy import copy
from typing import List, Union, Optional, Tuple

from hwt.code import If
from hwt.doc_markers import internal
from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Signal, HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import walkPhysInterfaces
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.clk_math import epsilon
from hwtHls.clk_math import start_clk
from hwtHls.netlist.codeOpsPorts import HlsOperationIn, HlsOperationOut
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.tmpVariable import HlsTmpVariable


IO_COMB_REALIZATION = OpRealizationMeta(latency_post=0.1e-9)

TimeSpec = Union[float, Tuple[float, ...]]


class AbstractHlsOp():
    """
    Abstract class for nodes in circuit which are subject to HLS scheduling

    :ivar name: optional suggested name for this object (for debbuging purposes)
    :ivar usedBy: for each output list of operation and its input index which are using this output
    :ivar dependsOn: for each input operation and index of its output with data required
        to perform this operation
    :ivar asap_start: scheduled time of start of operation using ASAP scheduler for each input
    :ivar asap_end: scheduled time of end of operation using ASAP scheduler for each output
    :ivar alap_start: scheduled time of start of operation using ALAP scheduler for each input
    :ivar alap_end: scheduled time of end of operation using ALAP scheduler for each output
    :ivar scheduledIn: final scheduled time of start of operation for each input
    :ivar scheduledInEnd: final scheduled time of end of operation for each output

    :attention: inputs must be soted 1st must have lowest latency

    :ivar latency_pre: combinational latency before first register
        in compoent for this operation (for each input)
    :ivar latency_post: combinational latency after last register
        in compoent for this operation (for each output, 0 corresponds to a same time as input[0])
    :ivar cycles_latency: number of clk cycles for data to get from input
        to output (for each output, 0 corresponds to a same clock cycle as input[0])
    :ivar cycles_dealy: number of clk cycles required to process data
         (for each output, 0 corresponds to a same clock cycle as input[0])
    """

    def __init__(self, parentHls: "HlsPipeline", name: str=None):
        self.name = name
        self.hls = parentHls

        self.usedBy: List[List[HlsOperationIn]] = []
        self.dependsOn: List[HlsOperationOut] = []

        self.asap_start: Optional[TimeSpec] = None
        self.asap_end: Optional[TimeSpec] = None
        self.alap_start: Optional[TimeSpec] = None
        self.alap_end: Optional[TimeSpec] = None
        # True if scheduled to specific time
        self.fixed_schedulation = False
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledInEnd: Optional[TimeSpec] = None

    def _numberForEachInput(self, val: Union[float, Tuple[float]]):
        if isinstance(val, (float, int)):
            return [val for _ in self.dependsOn]
        else:
            val = list(val)
            assert len(val) == self.dependsOn, (val, self.dependsOn)
            return val

    def _numberForEachOutput(self, val: Union[float, Tuple[float]]):
        if isinstance(val, (float, int)):
            return tuple(val for _ in self.usedBy)
        else:
            val = list(val)
            assert len(val) == self.usedBy
            return val

    def assignRealization(self, r: OpRealizationMeta):
        self.realization = r
        self.in_cycles_offset = self._numberForEachInput(copy(r.latency_pre))
        self.latency_pre = self._numberForEachInput(copy(r.latency_pre))
        self.latency_post = self._numberForEachOutput(copy(r.latency_post))
        self.cycles_latency = self._numberForEachOutput(copy(r.cycles_latency))
        self.cycles_delay = self._numberForEachOutput(copy(r.cycles_delay))

        return self

    def resolve_realization(self):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def get_earliest_clk(self):
        """Earliest schedule step (by ASAP)"""
        return start_clk(self.asap_start, self.hls.clk_period)

    def get_latest_clk(self):
        """Earliest schedule step (by ALAP)"""
        return start_clk(self.alap_start, self.hls.clk_period)

    def get_mobility(self):
        """
        :return: number of clk periods between earliest and latest schedulization time
        """
        m = self.get_latest_clk() - self.get_earliest_clk()
        assert m >= 0, (self, self.get_earliest_clk(),
                        self.get_latest_clk(),
                        self.asap_start / self.hls.clk_period,
                        self.alap_start / self.hls.clk_period)
        return m

    def get_probability(self, step):
        """Calculate probability of scheduling operation to this step"""
        if step < self.get_earliest_clk() or step > self.get_latest_clk():
            return 0.0

        return 1 / (self.get_mobility() + 1)

    def _get_rtl_context(self):
        return self.hls.ctx

    def instantiateHlsOperationInTime(self,
                                   allocator: "HlsAllocator",
                                   time:float,
                                   used_signals: UniqList[TimeIndependentRtlResourceItem]
                                   ) -> TimeIndependentRtlResourceItem:
        try:
            _o = allocator.node2instance[self]
        except KeyError:
            _o = None

        if _o is None:
            # if dependency of this node is not instantiated yet
            # instantiate it
            _o = allocator._instantiate(self, used_signals)
        else:
            used_signals.append(_o)

        return _o.get(time)


class HlsConst(AbstractHlsOp):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, val: HValue):
        self.val = val

        self.name = None
        self.hls = None
        # True if scheduled to specific time
        self.fixed_schedulation = True
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledInEnd: Optional[TimeSpec] = None

        self.usedBy: List[List[HlsOperationIn]] = [[], ]
        self.dependsOn: List[HlsOperationOut] = []

    def get(self, time: float):
        return self.val

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        s = self.val
        t = TimeIndependentRtlResource.INVARIANT_TIME
        return TimeIndependentRtlResource(s, t, allocator)

    @property
    def asap_start(self):
        return self.usedBy[0][0].obj.asap_start

    # @asap_start.setter
    # def asap_start(self, v):
    #    self.usedBy[0][0].obj.asap_start = v

    @property
    def asap_end(self):
        # (yes, the constant operation takes zero time that implies start = end)
        return self.usedBy[0][0].obj.asap_start

    # @asap_end.setter
    # def asap_end(self, v):
    #    self.usedBy[0][0].obj.asap_start = v

    @property
    def alap_start(self):
        return self.usedBy[0][0].obj.alap_start

    # @alap_start.setter
    # def alap_start(self, v):
    #    self.usedBy[0][0].obj.alap_start = v

    @property
    def alap_end(self):
        return self.usedBy[0][0].obj.alap_start

    # @alap_end.setter
    # def alap_end(self, v):
    #    self.usedBy[0][0].obj.alap_start = v

    def resolve_realization(self):
        pass


class HlsRead(AbstractHlsOp, HdlAssignmentContainer, InterfaceBase):
    """
    Hls plane to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar intf: original interface from which read should be performed
    """

    def __init__(self, parentHls: "HlsPipeline",
                 intf: Union[RtlSignal, Interface],
                 dst_intf: Union[RtlSignal, Interface, None]):
        AbstractHlsOp.__init__(self, parentHls, None)
        self.dependsOn.append(None)  # slot left for synchronization
        self.usedBy.append([])  # slot for data consummer
        self.operator = "read"
        HdlStatement.__init__(self)

        if isinstance(intf, RtlSignalBase):
            self._inputs.append(intf)
        elif isinstance(intf, Signal):
            self._inputs.append(intf._sig)
        else:
            assert isinstance(intf, (HsStructIntf, HandshakeSync)), intf
            if isinstance(intf, HsStructIntf):
                for s in walkPhysInterfaces(intf.data):
                    self._inputs.append(s._sig)

        # t = dataSig._dtype

        # from Assignment __init__
        self._now_is_event_dependent = False
        self.indexes = None
        self._instId = HdlAssignmentContainer._nextInstId()

        # instantiate signal for value from this read
        # self._sig = parentHls.ctx.sig(
        #    "hsl_" + getSignalName(intf),
        #    dtype=t)
        # self._sig.hidden =  False
        #
        # self._sig.origin = self
        # self._sig.drivers.append(self)
        if dst_intf is not None:
            self._outputs.append(dst_intf)
            dst_intf.drivers.append(self)
            dst_intf.origin = self
        self.dst = dst_intf
        self.src = intf

        # parentHls.inputs.append(self)

    def getRtlDataSig(self):
        intf = self.src
        if isinstance(intf, HsStructIntf):
            return intf.data
        else:
            return intf

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @internal
    def _destroy(self):
        HdlAssignmentContainer._destroy(self)
        self.hls.inputs.remove(self)

    def __repr__(self):
        return f"<{self.__class__.__name__:s}, {self.src}>"


class HlsWrite(AbstractHlsOp, HdlAssignmentContainer):
    """
    :ivar src: const value or HlsVariable
    :ivar dst: output interface not relatet to HLS
    """

    def __init__(self, parentHls: "HlsPipeline", src, dst: Union[RtlSignal, Interface, HlsTmpVariable]):
        AbstractHlsOp.__init__(self, parentHls, None)
        HdlStatement.__init__(self)
        self.dependsOn.append(None)
        self.usedBy.append([])
        self.operator = "write"
        self.src = src
        if isinstance(src, RtlSignal):
            src.endpoints.append(self)
            self._inputs.append(src)

        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (Signal, HlsIO)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp

        self.dst = dst
        # parentHls.outputs.append(self)
        if isinstance(dst, HlsIO):
            dst.drivers.append(self)
        else:
            assert isinstance(dst, (HlsOperationIn, HsStructIntf, Signal)), dst

        if indexCascade:
            for i in indexCascade:
                if isinstance(i, (Signal, HlsIO)):
                    self._inputs.append(i)

        if isinstance(dst, (HlsIO, RtlSignal)):
            self._outputs.append(dst)

        # from HdlAssignmentContainer.__init__
        self.isEventDependent = False
        self.indexes = indexCascade
        self._instId = HdlAssignmentContainer._nextInstId()
        # parentHls.ctx.statements.add(self)

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @internal
    def _destroy(self):
        HdlAssignmentContainer._destroy(self)
        self.hls.outputs.remove(self)

    def __repr__(self):
        if self.indexes:
            indexes = "[%r]" % self.indexes
        else:
            indexes = ""

        return f"<{self.__class__.__name__:s}, {self.dst}{indexes:s} <- {self.src}>"


class HlsOperation(AbstractHlsOp):
    """
    Abstract implementation of RTL operator

    :ivar operator: parent RTL operator for this hsl operator
    """

    def __init__(self, parentHls: "HlsPipeline",
                 operator: OpDefinition,
                 operand_cnt: int,
                 bit_length: int,
                 name=None):
        super(HlsOperation, self).__init__(parentHls, name=name)
        self.bit_length = bit_length
        self.operator = operator
        for _ in range(operand_cnt):
            self.dependsOn.append(None)
        # add containers for io pins
        self.usedBy.append([])

    def resolve_realization(self):
        hls = self.hls
        clk_period = hls.clk_period
        input_cnt = len(self.dependsOn)
        bit_length = self.bit_length

        if self.operator is AllOps.TERNARY:
            input_cnt = input_cnt // 2 + 1

        r = hls.platform.get_op_realization(
            self.operator, bit_length,
            input_cnt, clk_period)
        self.assignRealization(r)

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        op_out = HlsOperationOut(self, 0)
        try:
            return allocator.node2instance[op_out]
        except KeyError:
            pass

        operands = []
        for in_i, dep in enumerate(self.dependsOn):
            o = dep.obj
            _o = o.instantiateHlsOperationInTime(allocator, self.scheduledIn[in_i], used_signals)
            operands.append(_o)
        s = self.operator._evalFn(*(o.data for o in operands))

        if isinstance(s, HValue):
            t = TimeIndependentRtlResource.INVARIANT_TIME

        else:
            # create RTL signal expression base on operator type
            t = self.scheduledInEnd[0] + epsilon

        tis = TimeIndependentRtlResource(s, t, allocator)
        allocator._registerSignal(op_out, tis, used_signals)
        return tis

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.operator.id:s} {self.dependsOn}>"


class HlsMux(HlsOperation):
    """
    Multiplexer operation with one-hot encoded select signal
    """

    def __init__(self, parentHls, bit_length: int, name: str=None):
        super(HlsMux, self).__init__(
            parentHls, AllOps.TERNARY, 0, bit_length, name=name)
        self.elifs: List[Tuple[Optional[AbstractHlsOp], AbstractHlsOp]] = []

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        op_out = HlsOperationOut(self, 0)

        try:
            return allocator.node2instance[op_out]
        except KeyError:
            pass
        name = self.name
        mux_out_s = allocator._sig(name, self.elifs[0][1].obj.instantiateHlsOperationInTime(
            allocator, self.scheduledInEnd[0], used_signals).data._dtype)
        mux_top = None
        for elif_i, (c, v) in enumerate(self.elifs):
            if c is not None:
                c = c.obj.instantiateHlsOperationInTime(
                    allocator, self.scheduledIn[elif_i * 2], used_signals)
            v = v.obj.instantiateHlsOperationInTime(
                allocator,
                self.scheduledIn[elif_i * 2 + (1 if c is not None else 0)],
                used_signals)

            if mux_top is None:
                mux_top = If(c.data, mux_out_s(v.data))
            elif c is not None:
                mux_top.Elif(c.data, mux_out_s(v.data))
            else:
                mux_top.Else(mux_out_s(v.data))

        # create RTL signal expression base on operator type
        t = self.scheduledInEnd[0] + epsilon
        mux_out_s = TimeIndependentRtlResource(mux_out_s, t, allocator)
        allocator._registerSignal(op_out, mux_out_s, used_signals)
        return mux_out_s


class HlsIO(RtlSignal):
    """
    Signal which is connected to outside of HLS context
    """

    def __init__(self, hlsCntx, name: str, dtype:HdlType, def_val=None, nop_val=NOT_SPECIFIED):
        self.hlsCntx = hlsCntx
        RtlSignal.__init__(
            self, hlsCntx.ctx, name, dtype, def_val=def_val,
            nop_val=nop_val)
        self._interface = True

    def __call__(self, source) -> List[HdlAssignmentContainer]:
        source = toHVal(source, self._dtype)
        hls = self.hlsCntx
        w = HlsWrite(hls, source, self)
        hls.outputs.append(w)
        hls.ctx.statements.add(w)
        return [w, ]

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.name:s}>"
