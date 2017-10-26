from hwt.interfaces.std import Signal
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal


class ReadPromise(Signal):
    def __init__(self, hlsCtx, intf, latency):
        dataSig = intf._sig
        t = dataSig._dtype
        super(ReadPromise, self).__init__(dtype=t)
        self._sig = hlsCtx.ctx.sig("hsl_" + intf._name,
                                   dtype=t)
        self.hlsCtx = hlsCtx
        self.intf = intf
        self.latency = latency
        self._sig.drivers.append(self)


class WritePromise():
    def __init__(self, hlsCtx, what, where, latency):
        self.hlsCtx = hlsCtx
        self.what = what
        self.where = where
        self.latency = latency
        if isinstance(what, RtlSignal):
            what.endpoints.append(self)


class Hls():
    """
    High level synthesiser context
    """

    def __init__(self, parentUnit,
                 freq=None, maxLatency=None, resources=None):
        self.parentUnit = parentUnit
        self.freq = freq
        self.maxLatency = maxLatency
        self.resources = resources
        self.ctx = RtlNetlist()

    def read(self, intf, latency=0):
        """
        Scheduele read operation
        """
        return ReadPromise(self, intf, latency)

    def write(self, what, where, latency=1):
        """
        Scheduele write operation
        """
        return WritePromise(self, what, where, latency)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
