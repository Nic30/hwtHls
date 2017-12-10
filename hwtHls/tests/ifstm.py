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
            r = h.read
            a = r(self.a)
            b = r(self.b)
            c = r(self.c)

            d = self._sig("d_tmp", self.d._dtype)

            If(a,
                d(b),
            #).Elif(b,
            #    d(c),
            ).Else(
                d(c)
            )

            h.write(d, self.d)


if __name__ == "__main__":  # alias python main function
    from hwt.synthesizer.utils import toRtl

    u = SimpleIfStatementHls()
    p = VirtualHlsPlatform()
    print(toRtl(u, targetPlatform=p))
