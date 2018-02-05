
"""
Bernsteins Synthesis Algorithm - database key dependencies, Lazy Thinking
http://www.risc.jku.at/publications/download/risc_2335/2004-02-18-A.pdf
"""
from hwt.hdl.assignment import Assignment
from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.types.typeCast import toHVal
from hwt.interfaces.std import Signal
from hwt.synthesizer.andReducedContainer import AndReducedContainer
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.uniqList import UniqList
from hwtHls.clk_math import start_clk
from hwtHls.platform.opRealizationMeta import OpRealizationMeta,\
    UNSPECIFIED_OP_REALIZATION


IO_COMB_REALIZATION = OpRealizationMeta(latency_post=0.1e-9)


class AbstractHlsOp():
    """
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

    def __init__(self, parentHls, bit_length: int, name: str=None,
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

    def asHwt(self, serializer, ctx):
        return repr(self)


class HlsConst(AbstractHlsOp):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, val):
        self.name = None
        self.hls = None
        self.usedBy = UniqList()
        self.dependsOn = UniqList()
        self.val = val
        self.fixed_schedulation = True

    def get(self, time):
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


class HlsRead(AbstractHlsOp):
    """
    Hls plane to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar intf: original interface from which read should be performed
    """

    def __init__(self, parentHls, intf):
        AbstractHlsOp.__init__(self, parentHls, None)
        self.operator = "read"

        if isinstance(intf, RtlSignalBase):
            dataSig = intf
        else:
            dataSig = intf._sig

        t = dataSig._dtype

        # from Assignment __init__
        self.isEventDependent = False
        self.indexes = None
        self.cond = AndReducedContainer()
        self._instId = Assignment._nextInstId()

        # instantiate signal for value from this read
        self._sig = parentHls.ctx.sig(
            "hsl_" + getSignalName(intf),
            dtype=t)

        self._sig.origin = self
        self._sig.drivers.append(self)

        self.intf = intf

        parentHls.inputs.append(self)

    def getRtlDataSig(self):
        return self.intf

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def __repr__(self):
        return "<%s, %r>" % (self.__class__.__name__,
                             self.intf)


class HlsWrite(AbstractHlsOp, Assignment):
    """
    :ivar src: const value or HlsVariable
    :ivar dst: output interface not relatet to HLS
    """

    def __init__(self, hlsCtx, src, dst):
        AbstractHlsOp.__init__(self, hlsCtx, None)
        self.operator = "write"
        self.src = toHVal(src)

        if isinstance(dst, RtlSignal):
            if not isinstance(dst, Signal):
                tmp = dst._getIndexCascade()
                if tmp:
                    dst, indexCascade = tmp
                else:
                    indexCascade = None

        else:
            indexCascade = None

        if isinstance(src, RtlSignal):
            assert src.ctx is hlsCtx.ctx, \
                "Not mixing unit signals and HLS signals"
            src.endpoints.append(self)

        self.dst = dst

        # from Assignment __init__
        self.isEventDependent = False
        self.indexes = indexCascade
        self.cond = AndReducedContainer()
        self._instId = Assignment._nextInstId()

        hlsCtx.outputs.append(self)

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def __repr__(self):
        if self.indexes:
            indexes = "[%r]" % self.indexes
        else:
            indexes = ""

        return "<%s, %r <- %r%s>" % (self.__class__.__name__,
                                     self.dst, self.src, indexes)


class HlsOperation(AbstractHlsOp):
    """
    Abstract implementation of RTL operator

    :ivar operator: parent RTL operator for this hsl operator
    """

    def __init__(self, parentHls,
                 operator: OpDefinition, bit_length: int,  name=None):
        super(HlsOperation, self).__init__(parentHls, bit_length, name=name)
        self.operator = operator

    def resolve_realization(self):
        hls = self.hls
        clk_period = hls.clk_period
        input_cnt = len(self.dependsOn)
        bit_length = self.bit_length

        if self.operator is AllOps.TERNARY:
            input_cnt /= 2

        r = hls.platform.get_op_realization(
            self.operator, bit_length, input_cnt, clk_period)
        self.assignRealization(r)

    def __repr__(self):
        return "<%s %r %r>" % (self.__class__.__name__,
                               self.operator,
                               self.dependsOn)


class HlsMux(HlsOperation):
    """
    :note: dependsOn  in fommat [cond0, input0, cond1, intput1, ...]
    """

    def __init__(self, parentHls, bit_length: int, name: str=None):
        super(HlsMux, self).__init__(
            parentHls, AllOps.TERNARY, bit_length, name=name)


class HlsIO(RtlSignal):
    """
    Signal which is connected to outside of HLS context
    """

    def __repr__(self):
        return "<HlsIO %s>" % self.name
