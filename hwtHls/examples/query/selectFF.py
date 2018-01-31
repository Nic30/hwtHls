from typing import Union

from hwt.hdl.assignment import Assignment
from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.value import Value
from hwt.interfaces.std import Signal, Clk
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import toRtl


SigOrVal = Union[RtlSignal, Value]
AssigOrOp = Union[Assignment, Operator]


def reconnectDriverOf(sig: SigOrVal,
                      driver: AssigOrOp,
                      replacement: SigOrVal):
    sig.drivers.remove(driver)

    if isinstance(driver, Operator):
        raise NotImplementedError()
    elif isinstance(driver, Assignment):
        raise NotImplementedError()
    else:
        raise TypeError(driver)


def reconnectEndpointOf(sig: RtlSignal,
                        endpoint: AssigOrOp,
                        replacement: SigOrVal):
    sig.endpoints.remove(endpoint)

    if isinstance(endpoint, Operator):
        raise NotImplementedError()
    elif isinstance(endpoint, Assignment):
        raise NotImplementedError()
    else:
        raise TypeError(endpoint)


def disconnectDriverOf(sig: RtlSignal,
                       driver: AssigOrOp):
    sig.drivers.remove(driver)

    if isinstance(driver, Operator):
        raise NotImplementedError()
    elif isinstance(driver, Assignment):
        raise NotImplementedError()
    else:
        raise TypeError(driver)


def disconnectEndpointOf(sig: RtlSignal,
                         endpoint: AssigOrOp):
    sig.endpoints.remove(endpoint)

    if isinstance(endpoint, Operator):
        raise NotImplementedError()
    elif isinstance(endpoint, Assignment):
        raise NotImplementedError()
    else:
        raise TypeError(endpoint)


class FF_result():
    def __init__(self, clkSig, inputSig, regSig):
        self.clkSig = clkSig
        self.inputSig = inputSig
        self.regSig = regSig

    def __repr__(self):
        return "<FF_result clk:%r, inputSig:%r, regSig:%r>" % (
            self.clkSig, self.inputSig, self.regSig)

    def replace(self, newInput, newOutput):
        inp = self.inputSig
        assig = inp.drivers[0]
        if newInput is None:
            disconnectDriverOf(inp, assig)
        else:
            reconnectDriverOf(inp, assig, newInput)

        reg = self.regSig
        if newOutput is None:
            disconnectEndpointOf(reg, assig)
        else:
            for dst in reg.endpoints:
                reconnectEndpointOf(reg, dst, newOutput)


class FF_select():
    def __init__(self, unit: Unit):
        self.parent = unit

    def on_rising_edge_found(self, sig):
        for ep in sig.endpoints:
            if isinstance(ep, Assignment):
                if sig in ep.cond:
                    clk = sig.drivers[0].operands[0]
                    yield FF_result(clk, ep.src, ep.dst)

    def select(self):
        ctx = self.parent._cntx
        for sig in ctx.signals:
            if len(sig.drivers) == 1:
                driver = sig.drivers[0]
                if isinstance(driver, Operator):
                    if driver.operator == AllOps.RISING_EDGE:
                        yield from self.on_rising_edge_found(sig)


class OneFF(Unit):
    def _declr(self):
        self.clk = Clk()
        self.a = Signal()
        self.b = Signal()

    def _impl(self):
        r = self._reg
        a_reg = r("a_reg")
        a_reg(self.a)
        self.b(a_reg)

        s = FF_select(self)
        for ff in s.select():
            ff.replace(None, 1)


if __name__ == "__main__":
    toRtl(OneFF())
