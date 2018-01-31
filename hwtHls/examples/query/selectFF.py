from typing import Union

from hwt.hdl.assignment import Assignment
from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.value import Value
from hwt.interfaces.std import Signal, Clk
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import toRtl
from hwt.code import If, And
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist


SigOrVal = Union[RtlSignal, Value]
AssigOrOp = Union[Assignment, Operator]


class RtlNetlistManipulator():
    def __init__(self, cntx: RtlNetlist):
        self.cntx = cntx

    def reconnectDriverOf(self, sig: SigOrVal,
                          driver: AssigOrOp,
                          replacement: SigOrVal):
        sig.drivers.remove(driver)

        if isinstance(driver, Operator):
            raise NotImplementedError()
        elif isinstance(driver, Assignment):
            raise NotImplementedError()
        else:
            raise TypeError(driver)

    def reconnectEndpointsOf(self, sig: RtlSignal,
                             replacement: SigOrVal):
        for endpoint in sig.endpoints:
            if isinstance(endpoint, Operator):
                raise NotImplementedError()
            elif isinstance(endpoint, Assignment):
                a = endpoint
                if a.src is sig:
                    if a.indexes:
                        raise NotImplementedError()
                    self.destroyAssignment(a)
                    # [TODO] if type matches reuse old assignment
                    if a.cond:
                        If(And(*a.cond),
                           a.dst(replacement)
                           )
                    else:
                        a.dst(replacement)
                else:
                    raise NotImplementedError()
            else:
                raise TypeError(endpoint)

    def destroyAssignment(self, a: Assignment, disconnectDst=True, disconnectSrc=True):
        if a.indexes:
            for i in a.indexes:
                if isinstance(i, RtlSignal):
                    i.endpoints.remove(a)

        for c in a.cond:
            if isinstance(c, RtlSignal):
                c.endpoints.remove(a)

        if disconnectSrc:
            a.src.endpoints.remove(a)
        if disconnectDst:
            a.dst.drivers.remove(a)
        self.cntx.startsOfDataPaths.remove(a)

    def disconnectDriverOf(self, sig: RtlSignal,
                           driver: AssigOrOp):

        if isinstance(driver, Operator):
            raise NotImplementedError()
        elif isinstance(driver, Assignment):
            if driver.dst is sig:
                self.destroyAssignment(driver)
            else:
                raise NotImplementedError()
        else:
            raise TypeError(driver)

    def disconnectEndpointOf(self, sig: RtlSignal,
                             endpoint: AssigOrOp):
        sig.endpoints.remove(endpoint)

        if isinstance(endpoint, Operator):
            raise NotImplementedError()
        elif isinstance(endpoint, Assignment):
            raise NotImplementedError()
        else:
            raise TypeError(endpoint)


class FF_result():
    def __init__(self, parent, clkSig, inputSig, regSig):
        self.parent = parent
        self.clkSig = clkSig
        self.inputSig = inputSig
        self.regSig = regSig

    def __repr__(self):
        return "<FF_result clk:%r, inputSig:%r, regSig:%r>" % (
            self.clkSig, self.inputSig, self.regSig)

    def replace(self, newOutput, newInput):
        inp = self.inputSig
        assig = inp.drivers[0]
        m = RtlNetlistManipulator(self.parent.parent._cntx)
        if newInput is None:
            m.disconnectDriverOf(inp, assig)
        else:
            m.reconnectDriverOf(inp, assig, newInput)

        reg = self.regSig
        if newOutput is None:
            m.disconnectEndpointOf(reg, assig)
        else:
            m.reconnectEndpointsOf(reg, newOutput)


class FF_select():
    def __init__(self, unit: Unit):
        self.parent = unit

    def on_rising_edge_found(self, sig):
        for ep in sig.endpoints:
            if isinstance(ep, Assignment):
                if sig in ep.cond:
                    clk = sig.drivers[0].operands[0]
                    yield FF_result(self, clk, ep.src, ep.dst)

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
            ff.replace(1, None)


if __name__ == "__main__":
    print(toRtl(OneFF()))
