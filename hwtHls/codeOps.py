
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
from hwtHls.platform.opRealizationMeta import OpRealizationMeta,\
    UNSPECIFIED_OP_REALIZATION, EMPTY_OP_REALIZATION


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

    def asHwt(self, serializer, ctx):
        return repr(self)


class HlsConst(AbstractHlsOp):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, val):
        super(HlsConst, self).__init__(None, None)
        self.val = val

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


class HlsRead(AbstractHlsOp, Signal, Assignment):
    """
    Hls plane to read from interface

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar intf: original interface from which read should be performed
    """

    def __init__(self, parentHls, intf):
        AbstractHlsOp.__init__(self, parentHls, None)

        if isinstance(intf, RtlSignalBase):
            dataSig = intf
        else:
            dataSig = intf._sig

        t = dataSig._dtype
        Signal.__init__(self, dtype=t)

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
        self.assignRealization(EMPTY_OP_REALIZATION)

    def __repr__(self):
        return "<%s, %r>" % (self.__class__.__name__,
                             self.intf)


class HlsWrite(AbstractHlsOp, Assignment):
    """
    :ivar what: const value or HlsVariable
    :ivar where: output interface not relatet to HLS
    """

    def __init__(self, hlsCtx, what, where):
        AbstractHlsOp.__init__(self, hlsCtx, None)
        self.what = toHVal(what)

        if isinstance(where, RtlSignal):
            if not isinstance(where, Signal):
                tmp = where._getIndexCascade()
                if tmp:
                    where, indexCascade = tmp
                else:
                    indexCascade = None

        else:
            indexCascade = None

        if isinstance(what, RtlSignal):
            assert what.ctx is hlsCtx.ctx, \
                "Not mixing unit signals and HLS signals"
            what.endpoints.append(self)

        self.where = where

        # from Assignment __init__
        self.isEventDependent = False
        self.indexes = indexCascade
        self.cond = AndReducedContainer()
        self._instId = Assignment._nextInstId()

        hlsCtx.outputs.append(self)

    def resolve_realization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    def __repr__(self):
        if self.indexes:
            indexes = "[%r]" % self.indexes
        else:
            indexes = ""

        return "<%s, %r <- %r%s>" % (self.__class__.__name__,
                                     self.where, self.what, indexes)


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
