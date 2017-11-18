
"""
Bernsteins Synthesis Algorithm - database key dependencies, Lazy Thinking
http://www.risc.jku.at/publications/download/risc_2335/2004-02-18-A.pdf
"""
from hwt.hdl.operatorDefs import OpDefinition
from hwt.hdl.types.typeCast import toHVal
from hwt.interfaces.std import Signal
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.uniqList import UniqList
from hwt.hdl.assignment import Assignment
from hwt.synthesizer.andReducedContainer import AndReducedContainer


class AbstractHlsOp():
    """
    :ivar usedBy: unique list of operations which are using data from this
        operation
    :ivar dependsOn: unique list of operations which data are required
        to perform this operation
    :ivar asap_start: scheduled time of start of operation using ASAP scheduler
    :ivar asap_end: scheduled time of end of operation using ASAP scheduler
    :ivar alap_start: scheduled time of start of operation using ALAP scheduler
    :ivar alap_end: scheduled time of end of operation using ALAP scheduler
    :ivar latency_pre: combinational latency before first register
        in compoent for this operation
    :ivar latency_post: combinational latency after last register
        in compoent for this operation
    :ivar cycles_latency: number of clk cycles for data to get from input
        to output
    :ivar cycles_dealy: number of clk cycles required to process data
    """

    def __init__(self, parentHls, latency_pre=0, latency_post=0,
                 cycles_latency=0, cycles_delay=0):
        self.hls = parentHls
        self.usedBy = UniqList()
        self.dependsOn = UniqList()
        self.asap_start, self.asap_end = None, None
        self.alap_start, self.alap_end = None, None
        self.latency_pre = latency_pre
        self.latency_post = latency_post
        self.cycles_latency = cycles_latency
        self.cycles_delay = cycles_delay


class HlsConst(AbstractHlsOp):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, val):
        self.usedBy = UniqList()
        self.dependsOn = UniqList()
        self.latency_pre = 0
        self.latency_post = 0
        self.cycles_latency = 0
        self.cycles_delay = 0
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
    * 

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar intf: original interface from which read should be performed
    """

    def __init__(self, parentHls, intf, latency):
        if isinstance(intf, RtlSignalBase):
            dataSig = intf
        else:
            dataSig = intf._sig

        t = dataSig._dtype

        AbstractHlsOp.__init__(self, parentHls, latency)
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

    def __repr__(self):
        return "<%s, %r>" % (self.__class__.__name__,
                             self.intf)


class HlsWrite(AbstractHlsOp, Assignment):
    """
    :ivar what: const value or HlsVariable
    :ivar where: output interface not relatet to HLS
    """

    def __init__(self, hlsCtx, what, where, latency):
        AbstractHlsOp.__init__(self, hlsCtx, latency_pre=latency)
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
                 operator: OpDefinition):
        latencies = parentHls.platform.OP_LATENCIES
        super(HlsOperation, self).__init__(
            parentHls, latency_pre=latencies[operator])
        self.operator = operator

    def __repr__(self):
        return "<%s %r %r>" % (self.__class__.__name__,
                               self.operator,
                               self.dependsOn)
