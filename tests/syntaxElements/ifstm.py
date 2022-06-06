#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtLib.examples.statements.ifStm import SimpleIfStatement


class SimpleIfStatementHls(SimpleIfStatement):

    def _config(self):
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        super(SimpleIfStatementHls, self)._declr()

    def _impl(self):
        hls = HlsStreamProc(self)
        r = hls.read
        a = r(self.a)
        b = r(self.b)
        c = r(self.c)
        tmp = hls.var("tmp", self.d._dtype)
        hls.thread(
            hls.While(True,
                a, b, c,
                hls.If(a,
                    tmp(b),
                ).Elif(b, # this elif is redundant
                    tmp(c),
                ).Else(
                    tmp(c)
                ),
                hls.write(tmp, self.d)
            )
        )
        hls.compile()



if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = SimpleIfStatementHls()
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
