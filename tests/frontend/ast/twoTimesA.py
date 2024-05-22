#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.constants import Time
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from tests.baseSsaTest import BaseSsaTC


class TwoTimesA0(HwModule):

    def _config(self):
        self.CLK_FREQ = int(100e6)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        self.a = HwIOVectSignal(8)
        self.b = HwIOVectSignal(8)._m()

    def _impl(self):
        hls = HlsScope(self)
        # a = hls.read(self.a).data
        a = hls.var("a", self.a._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                a(hls.read(self.a).data),
                hls.write(a + a, self.b)
            ),
            self._name)
        )
        hls.compile()


class TwoTimesA1(TwoTimesA0):

    def _impl(self):
        hls = HlsScope(self)
        a = hls.read(self.a).data
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(a + a, self.b)
            ),
            self._name)
        )
        hls.compile()


class TwoTimesA_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_TwoTimesA0(self):
        self._test_simple(TwoTimesA0)
        self._test_ll(TwoTimesA0)

    def test_TwoTimesA1(self):
        self._test_simple(TwoTimesA1)
        self._test_ll(TwoTimesA1)

    def _test_simple(self, cls):
        dut = cls()
        a = 20
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.a._ag.data.append(a)

        self.runSim(40 * Time.ns)

        res = dut.b._ag.data[-1]
        self.assertValEqual(res, a + a)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # m = TwoTimesA0()
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([TwoTimesA_TC('test_TwoTimesA0')])
    suite = testLoader.loadTestsFromTestCase(TwoTimesA_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
