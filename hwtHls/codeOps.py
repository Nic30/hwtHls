from typing import List, Union, Optional, Tuple

from hwt.doc_markers import internal
from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from hwt.hdl.value import HValue
from hwt.interfaces.std import Signal
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.clk_math import start_clk
from hwtHls.platform.opRealizationMeta import OpRealizationMeta, \
    UNSPECIFIED_OP_REALIZATION
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import walkPhysInterfaces
from hwt.interfaces.hsStructIntf import HsStructIntf

IO_COMB_REALIZATION = OpRealizationMeta(latency_post=0.1e-9)


class AbstractHlsOp():
    """
    Abstract class for nodes in circuit which are subject to HLS scheduling

    :ivar name: optional suggested name for this object
    :ivar usedBy: unique list of operations which are using data from this
        operation
    :ivar dependsOn: unique list of operations which data are required
        to perform this operation
    :ivar asap_start: scheduled time of start of operation using ASAP scheduler
    :ivar asap_end: scheduled time of end of operation using ASAP scheduler
    :ivar alap_start: scheduled time of start of operation using ALAP scheduler
    :ivar alap_end: scheduled time of end of operation using ALAP scheduler
    :ivar scheduledIn: final scheduled time of start of operation
    :ivar scheduledInEnd: final scheduled time of end of operation
    :ivar latency_pre: combinational latency before first register
        in compoent for this operation
    :ivar latency_post: combinational latency after last register
        in compoent for this operation
    :ivar cycles_latency: number of clk cycles for data to get from input
        to output
    :ivar cycles_dealy: number of clk cycles required to process data
    """

    def __init__(self, parentHls: "Hls", bit_length: int, name: str=None,
                 realization: OpRealizationMeta=UNSPECIFIED_OP_REALIZATION):
        self.name = name
        self.hls = parentHls
        self.usedBy = UniqList()
        self.dependsOn = UniqList()
        self.bit_length = bit_length

        self.asap_start, self.asap_end = None, None
        self.alap_start, self.alap_end = None, None
        # True if scheduled to specific time
        self._earliest, self._latest = None, None
        self.fixed_schedulation = False
        self.scheduledIn, self.scheduledInEnd = None, None
        self.assignRealization(realization)

    def assignRealization(self, r: OpRealizationMeta):
        self.realization = r
        self.latency_pre = r.latency_pre
        self.latency_post = r.latency_post
        self.cycles_latency = r.cycles_latency
        self.cycles_delay = r.cycles_delay

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


class HlsConst(AbstractHlsOp):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, val: HValue):
        self.name = None
        self.hls = None
        self.usedBy = UniqList()
        self.dependsOn = UniqList()
        self.val = val
        self.fixed_schedulation = True

    def get(self, time: float):
        return self.val

    @property
    def asap_start(self):
        return self.usedBy[0].asap_start

    @property
    def asap_end(self):
        return self.usedBy[0].asap_start

    @property
    def alap_start(self):
        return self.usedBy[0].alap_start

    @property
    def alap_end(self):
        return self.usedBy[0].alap_start

    def resolve_realization(self):
        pass


class HlsRead(AbstractHlsOp, HdlAssignmentContainer):
    """
    Hls plane to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar intf: original interface from which read should be performed
    """

    def __init__(self, parentHls: "Hls",
                 intf: Union[RtlSignal, Interface],
                 dst_intf: Union[RtlSignal, Interface]):
        AbstractHlsOp.__init__(self, parentHls, None)
        self.operator = "read"
        HdlStatement.__init__(self)

        if isinstance(intf, RtlSignalBase):
            self._inputs.append(intf)
        elif isinstance(intf, Signal):
            self._inputs.append(intf._sig)
        else:
            assert isinstance(intf, HsStructIntf), intf
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

        self._outputs.append(dst_intf)
        dst_intf.drivers.append(self)
        dst_intf.origin = self
        self.dst = dst_intf

        self.intf = intf

        parentHls.inputs.append(self)

    def getRtlDataSig(self):
        intf = self.intf
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
        return f"<{self.__class__.__name__:s}, {self.intf}>"


class HlsWrite(AbstractHlsOp, HdlAssignmentContainer):
    """
    :ivar src: const value or HlsVariable
    :ivar dst: output interface not relatet to HLS
    """

    def __init__(self, parentHls: "Hls", src, dst):
        AbstractHlsOp.__init__(self, parentHls, None)
        HdlStatement.__init__(self)
        self.operator = "write"
        self.src = toHVal(src)

        indexCascade = None
        if isinstance(dst, RtlSignal):
            if not isinstance(dst, (Signal, HlsIO)):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade, _ = tmp

        if isinstance(src, RtlSignal):
            src.endpoints.append(self)
        dst.drivers.append(self)
        self.dst = dst
        if isinstance(dst, HlsIO):
            parentHls.outputs.append(self)

        self._inputs.append(src)
        if indexCascade:
            for i in indexCascade:
                if isinstance(i, (Signal, HlsIO)):
                    self._inputs.append(i)
        self._outputs.append(dst)

        # from Assignment __init__
        self.isEventDependent = False
        self.indexes = indexCascade
        self._instId = HdlAssignmentContainer._nextInstId()
        parentHls.ctx.statements.add(self)

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

    def __init__(self, parentHls: "Hls",
                 operator: OpDefinition,
                 bit_length: int,
                 name=None):
        super(HlsOperation, self).__init__(parentHls, bit_length, name=name)
        self.operator = operator

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

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.operator} {self.dependsOn}>"


class HlsMux(HlsOperation):

    def __init__(self, parentHls, bit_length: int, name: str=None):
        super(HlsMux, self).__init__(
            parentHls, AllOps.TERNARY, bit_length, name=name)
        self.elifs: Tuple[Optional[AbstractHlsOp], AbstractHlsOp] = []


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
        return [HlsWrite(self.hlsCntx, source, self), ]

    def __repr__(self):
        return "<HlsIO %s>" % self.name
