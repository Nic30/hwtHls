#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC


class HlsAstExprTree3_example(Unit):

    def _config(self):
        self.CLK_FREQ = Param(int(40e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)
        self.c = VectSignal(32, signed=False)
        self.d = VectSignal(32, signed=False)

        self.x = VectSignal(32, signed=False)
        self.y = VectSignal(32, signed=False)
        self.z = VectSignal(32, signed=False)
        self.w = VectSignal(32, signed=False)

        self.f1 = VectSignal(32, signed=False)._m()
        self.f2 = VectSignal(32, signed=False)._m()
        self.f3 = VectSignal(32, signed=False)._m()

    def _impl(self):
        hls = HlsScope(self)
        r = hls.read
        a, b, c, d = r(self.a), r(self.b), r(self.c), r(self.d)
        x, y, z, w = r(self.x), r(self.y), r(self.z), r(self.w)

        f1 = (a + b + c) * d
        xy = x + y
        f2 = xy * z
        f3 = xy * w

        wr = hls.write
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                a, b, c, d,
                wr(f1, self.f1),
                wr(f2, self.f2),
                wr(f3, self.f3),
            ),
            self._name)
        )
        hls.compile()



class HlsAstExprTree3_example_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_ll(self):
        self._test_ll(HlsAstExprTree3_example)

    def test_simple(self):
        u = HlsAstExprTree3_example()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.a._ag.data.append(3)
        u.b._ag.data.append(4)
        u.c._ag.data.append(5)
        u.d._ag.data.append(6)
        u.x._ag.data.append(7)
        u.y._ag.data.append(8)
        u.z._ag.data.append(9)
        u.w._ag.data.append(10)

        self.runSim(int(7 * freq_to_period(u.CLK_FREQ)))

        self.assertValEqual(u.f1._ag.data[-1], (3 + 4 + 5) * 6)
        self.assertValEqual(u.f2._ag.data[-1], (7 + 8) * 9)
        self.assertValEqual(u.f3._ag.data[-1], (7 + 8) * 10)


if __name__ == "__main__":
    import unittest
    # from hwt.synthesizer.utils import to_rtl_str
    # u = HlsAstExprTree3_example()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))

    suite = unittest.TestSuite()
    # suite.addTest(HlsAstExprTree3_example_TC('test_simple'))
    suite.addTest(unittest.makeSuite(HlsAstExprTree3_example_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
