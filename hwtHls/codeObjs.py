
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

    def __init__(self, latency_pre, latency_post=0,
                 cycles_latency=0, cycles_delay=0):
        self.usedBy = UniqList()
        self.dependsOn = UniqList()
        self.asap_start, self.asap_end = None, None
        self.alap_start, self.alap_end = None, None
        self.latency_pre = latency_pre
        self.latency_post = latency_post
        self.cycles_latency = cycles_latency
        self.cycles_delay = cycles_delay


class HlsConst(AbstractHlsOp):
    def __init__(self, val):
        super(HlsConst, self).__init__(latency=0)
        self.val = val

    def get(self, time):
        return self.val


class ReadOpPromise(Signal, AbstractHlsOp):
    def __init__(self, hlsCtx, intf, latency):
        if isinstance(intf, RtlSignalBase):
            dataSig = intf
        else:
            dataSig = intf._sig

        t = dataSig._dtype

        AbstractHlsOp.__init__(self, latency)
        Signal.__init__(self, dtype=t)

        self._sig = hlsCtx.ctx.sig("hsl_" + getSignalName(intf),
                                   dtype=t)

        self._sig.origin = self
        self._sig.drivers.append(self)

        self.hlsCtx = hlsCtx
        self.intf = intf

        hlsCtx.inputs.append(self)

    def getRtlDataSig(self):
        return self.intf

    def __repr__(self):
        return "<%s, %r, latency=%d>" % (self.__class__.__name__,
                                         self.intf, self.latency)


class WriteOpPromise(AbstractHlsOp):
    """
    :ivar what: const value or HlsVariable
    :ivar where: output interface not relatet to HLS
    """

    def __init__(self, hlsCtx, what, where, latency):
        super(WriteOpPromise, self).__init__(latency_pre=latency)
        self.hlsCtx = hlsCtx
        self.what = toHVal(what)
        self.where = where
        if isinstance(what, RtlSignal):
            what.endpoints.append(self)

        hlsCtx.outputs.append(self)


class HlsOperation(AbstractHlsOp):
    """
    Abstract implementation of RTL operator

    :ivar parentHls: Hls instance where is schedueling performed
    :ivar operator: parent RTL operator for this hsl operator
    """

    def __init__(self,
                 operator: OpDefinition,
                 parentHls):
        latencies = parentHls.platform.OP_LATENCIES
        super(HlsOperation, self).__init__(latency_pre=latencies[operator])
        self.parentHls = parentHls
        self.operator = operator

    def __repr__(self):
        return "<%s %r %r>" % (self.__class__.__name__,
                               self.operator,
                               self.dependsOn)


class FsmNode():
    """
        -------
 lValid>|     |>rValid
        |     |
 lReady<|     |<rReady
        -------

    """

    def __init__(self):
        self.ldata = None
        self.lReady = None
        self.lValid = None

        self.rdata = None
        self.rReady = None
        self.rValid = None

    def isClkDependent(self):
        raise NotImplementedError()
