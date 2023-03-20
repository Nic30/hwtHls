#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.examples.statements.ifStm import SimpleIfStatement
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import get_bit
from tests.baseSsaTest import BaseSsaTC


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
                ast.If(a.data,
                    tmp(b.data),
                ).Elif(b.data,  # this elif is redundant
                    tmp(c.data),
                ).Else(
                    tmp(c.data)
                ),
                hls.write(tmp, self.d)
            ),
            self._name)
        )
        hls.compile()


class HlsSimpleIfStatement_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_simple(self):
        u = HlsSimpleIfStatement()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        for i in range(1 << 3):
            u.a._ag.data.append(get_bit(i, 0))
            u.b._ag.data.append(get_bit(i, 1))
            u.c._ag.data.append(get_bit(i, 2))

        def model(a, b, c):
            if a:
                return b
            elif b:
                return c
            else:
                return c

        d = [model(*args) for args in zip(u.a._ag.data, u.b._ag.data, u.c._ag.data)]

        self.runSim(int((len(d) + 1) * freq_to_period(u.CLK_FREQ)))

        self.assertValSequenceEqual(u.d._ag.data, d)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = HlsSimpleIfStatement()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(u, target_platform=p))

    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(HlsAstExprTree3_example_TC('test_simple'))
    suite.addTest(unittest.makeSuite(HlsSimpleIfStatement_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
