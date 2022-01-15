#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.platform.virtual import VirtualHlsPlatform
from tests.syntaxElements.baseSsaTest import BaseSsaTC


class TwoTimesA0(Unit):

    def _config(self):
        self.CLK_FREQ = int(100e6)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        self.a = VectSignal(8)
        self.b = VectSignal(8)._m()

    def _impl(self):
        hls = HlsStreamProc(self)
        # a = hls.read(self.a)
        a = hls.var("a", self.a._dtype)
        hls.thread(
            hls.While(True,
                a(hls.read(self.a)),
                hls.write(a + a, self.b)
            )
        )
        # hls.thread(
        #    hls.While(True,
        #        hls.write(a + a, self.b)
        #    )
        # )


class TwoTimesA1(TwoTimesA0):

    def _impl(self):
        hls = HlsStreamProc(self)
        a = hls.read(self.a)
        hls.thread(
           hls.While(True,
               hls.write(a + a, self.b)
           )
        )


class TwoTimesA_TC(BaseSsaTC):
    __FILE__ = __file__

    def test0(self):
        self._test_simple(TwoTimesA0)
        self._test_ll(TwoTimesA0)

    def test1(self):
        self._test_simple(TwoTimesA1)
        self._test_ll(TwoTimesA1)

    def _test_simple(self, cls):
        u = cls()
        a = 20
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.a._ag.data.append(a)

        self.runSim(40 * Time.ns)

        res = u.b._ag.data[-1]
        self.assertValEqual(res, a + a)


if __name__ == "__main__":
    # from hwt.synthesizer.utils import to_rtl_str
    # u = TwoTimesA0()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))

    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(TwoTimesA_TC('_test_simple'))
    suite.addTest(unittest.makeSuite(TwoTimesA_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
