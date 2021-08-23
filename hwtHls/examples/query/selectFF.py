#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.interfaces.std import Signal, Clk
from hwt.synthesizer.unit import Unit
from hwtHls.query.rtlNetlistManipulator import RtlNetlistManipulator


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
        m = RtlNetlistManipulator(self.parent)
        if newInput is None:
            m.disconnect_driver_of(inp, assig)
        else:
            m.reconnectDriverOf(inp, assig, newInput)

        reg = self.regSig
        if newOutput is None:
            m.disconnect_endpoint_of(reg, assig)
        else:
            m.reconnect_endpoints_of(reg, newOutput)


class FF_select():

    def __init__(self, ctx: Unit):
        self.ctx = ctx

    def on_rising_edge_found(self, sig):
        for ep in sig.endpoints:
            if isinstance(ep, HdlAssignmentContainer):
                if sig in ep.cond:
                    clk = sig.drivers[0].operands[0]
                    yield FF_result(self, clk, ep.src, ep.dst)

    def select(self):
        for sig in self.ctx.signals:
            if len(sig.drivers) == 1:
                driver = sig.drivers[0]
                if isinstance(driver, Operator):
                    if driver.operator == AllOps.RISING_EDGE:
                        yield from self.on_rising_edge_found(sig)


class OneFF(Unit):

    def _declr(self):
        self.clk = Clk()
        self.a = Signal()
        self.b = Signal()._m()

    def _impl(self):
        r = self._reg
        a_reg = r("a_reg")
        a_reg(self.a)
        self.b(a_reg)

        s = FF_select(self._ctx)
        for ff in s.select():
            ff.replace(1, None)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    print(to_rtl_str(OneFF()))
