#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.baseSsaTest import BaseSsaTC


class ReadIfOtherEqual(Unit):

    def _config(self):
        self.FREQ = Param(int(100e6))
        self.DATA_WIDTH = Param(8)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        with self._paramsShared():
            self.a = Handshaked()
            self.b = Handshaked()

    def _impl(self) -> None:
        hls = HlsScope(self, freq=self.FREQ)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                ast.If(hls.read(self.a).data._eq(3),
                   hls.read(self.b),
                )
            ),
            self._name)
        )
        hls.compile()


class ReadIfOtherEqualOnce(ReadIfOtherEqual):

    def _impl(self) -> None:
        hls = HlsScope(self, freq=self.FREQ)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.If(hls.read(self.a).data._eq(3),
               hls.read(self.b),
            ),
            self._name)
        )
        hls.compile()


class HlsAstReadIfTc(BaseSsaTC):
    __FILE__ = __file__

    def test_ReadIfOtherEqual_ll(self):
        self._test_ll(ReadIfOtherEqual)

    def test_ReadIfOtherEqualOnce_ll(self):
        self._test_ll(ReadIfOtherEqualOnce)

    def testReadIfOtherEqual_50M(self, f=50e6):
        self.testReadIfOtherEqual_100M(f)

    def testReadIfOtherEqual_100M(self, f=100e6):
        u = ReadIfOtherEqual()
        u.FREQ = int(f)
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.a._ag.data.extend([0, 3, 3, 0, 3, 0, 0, ])
        u.b._ag.data.extend(range(10))
        self.runSim((len(u.a._ag.data) + 15) * int(freq_to_period(f)))
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        self.assertSequenceEqual(u.a._ag.data, [])
        self.assertSequenceEqual(u.b._ag.data, [4, 5, 6, 7, 8, 9])

    def testReadIfOtherEqual_150M(self, f=150e6):
        self.testReadIfOtherEqual_100M(f)

    def _testReadIfOtherEqualOnce(self, a, res, f:float):
        u = ReadIfOtherEqualOnce()
        u.FREQ = int(f)
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.a._ag.data.append(a)
        u.b._ag.data.extend(range(5))
        self.runSim(5 * int(freq_to_period(f)))
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        self.assertSequenceEqual(u.a._ag.data, [])
        self.assertSequenceEqual(u.b._ag.data, res)

    def testReadIfOtherEqualOnce_noread_50M(self):
        self._testReadIfOtherEqualOnce(0, list(range(1, 5)), 50e6)

    def testReadIfOtherEqualOnce_read_50M(self):
        self._testReadIfOtherEqualOnce(3, list(range(2, 5)), 50e6)

    def testReadIfOtherEqualOnce_noread_100M(self):
        self._testReadIfOtherEqualOnce(0, list(range(1, 5)), 100e6)

    def testReadIfOtherEqualOnce_read_100M(self):
        self._testReadIfOtherEqualOnce(3, list(range(2, 5)), 100e6)

    def testReadIfOtherEqualOnce_noread_150M(self):
        self._testReadIfOtherEqualOnce(0, list(range(1, 5)), 150e6)

    def testReadIfOtherEqualOnce_read_150M(self):
        self._testReadIfOtherEqualOnce(3, list(range(2, 5)), 150e6)


if __name__ == '__main__':
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # u = ReadIfOtherEqual()
    # # u.DATA_WIDTH = 8
    # u.FREQ = int(150e6)
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsAstReadIfTc("testReadIfOtherEqual_150M")])
    suite = testLoader.loadTestsFromTestCase(HlsAstReadIfTc)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
