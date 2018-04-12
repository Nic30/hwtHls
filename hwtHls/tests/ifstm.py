#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.code import If
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.samples.statements.ifStm import SimpleIfStatement


class SimpleIfStatementHls(SimpleIfStatement):
    def _config(self):
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        super(SimpleIfStatementHls, self)._declr()

    def _impl(self):
        with Hls(self, freq=self.CLK_FREQ) as h:
            io = h.io
            a = io(self.a)
            b = io(self.b)
            c = io(self.c)
            d = io(self.d)

            If(a,
                d(b),
            ).Elif(b,
                d(c),
            ).Else(
                d(c)
            )


if __name__ == "__main__":  # alias python main function
    from hwt.synthesizer.utils import toRtl

    u = SimpleIfStatementHls()
    p = VirtualHlsPlatform()
    print(toRtl(u, targetPlatform=p))
