#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scheduler.scheduler import TimeConstraintError


class AlapAsapDiffExample(Unit):
    def _config(self):
        self.CLK_FREQ = int(500e6)

    def _declr(self):
        addClkRstn(self)
        self.a = VectSignal(8)
        self.b = VectSignal(8)
        self.c = VectSignal(8)
        self.d = VectSignal(8)._m()

    def _impl(self):
        with HlsPipeline(self, freq=self.CLK_FREQ) as hls:
            # inputs has to be readed to enter hls scope
            # (without read() operation will not be schedueled by HLS
            #  but they will be directly synthesized)
            a, b, c = [hls.io(intf)
                       for intf in [self.a, self.b, self.c]]
            # depending on target platform this expresion
            # can be mapped to DPS, LUT, etc...
            # no constrains are specified => default strategy is
            # to achieve zero delay and minimum latency, for this CLK_FREQ
            d = ~(~a & ~b) & ~c

            hls.io(self.d)(d)


def neg_8b(a):
    return ~a & 0xff


class AlapAsapDiffExample_TC(SimTestCase):
    def test_500MHz(self):
        self._test_simple(500e6)

    def test_200MHz(self):
        self._test_simple(200e6)

    def test_1Hz(self):
        self._test_simple(1)

    def test_1GHz_fail(self):
        with self.assertRaises(TimeConstraintError):
            self._test_simple(1e9)

    def _test_simple(self, freq):
        u = AlapAsapDiffExample()
        u.CLK_FREQ = int(freq)
        a = 20
        b = 58
        c = 48
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.a._ag.data.append(a)
        u.b._ag.data.append(b)
        u.c._ag.data.append(c)

        self.runSim(40 * Time.ns)

        res = u.d._ag.data[-1]
        self.assertValEqual(res, neg_8b(neg_8b(a) & neg_8b(b)) & neg_8b(c))


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    u = AlapAsapDiffExample()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))

    suite = unittest.TestSuite()
    # suite.addTest(FrameTmplTC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(AlapAsapDiffExample_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
