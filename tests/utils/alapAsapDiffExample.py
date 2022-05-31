#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtSimApi.utils import freq_to_period


class AlapAsapDiffExample(Unit):

    def _config(self):
        self.CLK_FREQ = int(400e6)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        self.a = VectSignal(8)
        self.b = VectSignal(8)
        self.c = VectSignal(8)
        self.d = VectSignal(8)._m()

    def _impl(self):
        hls = HlsStreamProc(self)
        # inputs has to be readed to enter hls scope
        # (without read() operation will not be schedueled by HLS
        #  but they will be directly synthesized)
        a, b, c = [hls.read(intf) for intf in [self.a, self.b, self.c]]
        # depending on target platform this expresion
        # can be mapped to DPS, LUT, etc...
        # no constrains are specified => default strategy is
        # to achieve zero delay and minimum latency, for this CLK_FREQ
        d = ~(~a & ~b) & ~c

        hls.thread(
            hls.While(True,
                hls.write(d, self.d)
            )
        )
        hls.compile()



def neg_8b(a):
    return ~a & 0xff


class AlapAsapDiffExample_TC(SimTestCase):

    def test_400MHz(self):
        self._test_simple(400e6)

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

        self.runSim(int(40 * freq_to_period(u.CLK_FREQ)))

        res = u.d._ag.data[-1]
        self.assertValEqual(res, neg_8b(neg_8b(a) & neg_8b(b)) & neg_8b(c))


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    u = AlapAsapDiffExample()
    from hwtHls.platform.virtual import makeDebugPasses
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))

    #suite = unittest.TestSuite()
    ## suite.addTest(FrameTmplTC('test_frameHeader'))
    #suite.addTest(unittest.makeSuite(AlapAsapDiffExample_TC))
    #runner = unittest.TextTestRunner(verbosity=3)
    #runner.run(suite)
