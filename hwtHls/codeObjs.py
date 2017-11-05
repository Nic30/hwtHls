
"""
Bernsteins Synthesis Algorithm - database key dependencies, Lazy Thinking
http://www.risc.jku.at/publications/download/risc_2335/2004-02-18-A.pdf
"""
from hwt.hdl.operatorDefs import OpDefinition
from hwt.interfaces.std import Signal
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.uniqList import UniqList
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.hdl.types.typeCast import toHVal


class AbstractHlsOp():
    def __init__(self, latency):
        self.usedBy = UniqList()
        self.dependsOn = UniqList()
        self.latency = latency


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
        super(WriteOpPromise, self).__init__(latency=latency)
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
    :ivar pre_delay: wire delay from input to outputs or next clock cycles
    :ivar pot_delay: wire delay after last clock cycle (or 0)
    :ivar latency: computational latency of pipelined operation
        (0 == combinational component)
    :ivar cycles: computational delay of operation (0 == result every cycle)
    """

    def __init__(self,
                 operator: OpDefinition,
                 parentHls,
                 onUpdateFn=None):
        super(HlsOperation, self).__init__(latency=0)
        self.parentHls = parentHls
        self.pre_delay = 0
        self.post_delay = 0
        self.cycles = 0

        self.operator = operator
        self.onUpdateFn = onUpdateFn

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
