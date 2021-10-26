#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import If
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.examples.statements.ifStm import SimpleIfStatement


class SimpleIfStatementHls(SimpleIfStatement):

    def _config(self):
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        super(SimpleIfStatementHls, self)._declr()

    def _impl(self):
        with HlsPipeline(self, freq=self.CLK_FREQ) as h:
            io = h.io
            a = io(self.a)
            b = io(self.b)
            c = io(self.c)
            tmp = h.var("tmp", self.d._dtype)
            d = io(self.d)

            If(a,
                tmp(b),
            ).Elif(b,
                tmp(c),
            ).Else(
                tmp(c)
            )
            d(tmp)


if __name__ == "__main__":  # alias python main function
    from hwt.synthesizer.utils import to_rtl_str

    u = SimpleIfStatementHls()
    p = VirtualHlsPlatform()
    print(to_rtl_str(u, target_platform=p))
