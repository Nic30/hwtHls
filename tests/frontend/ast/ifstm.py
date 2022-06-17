#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.examples.statements.ifStm import SimpleIfStatement


class HlsSimpleIfStatement(SimpleIfStatement):

    def _config(self):
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        super(HlsSimpleIfStatement, self)._declr()

    def _impl(self):
        hls = HlsScope(self)
        r = hls.read
        a = r(self.a)
        b = r(self.b)
        c = r(self.c)
        tmp = hls.var("tmp", self.d._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                a, b, c,
                ast.If(a,
                    tmp(b),
                ).Elif(b,  # this elif is redundant
                    tmp(c),
                ).Else(
                    tmp(c)
                ),
                hls.write(tmp, self.d)
            ),
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = HlsSimpleIfStatement()
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
