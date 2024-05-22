#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class AlapAsapDiffExample(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = int(400e6)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        self.a = HwIOVectSignal(8)
        self.b = HwIOVectSignal(8)
        self.c = HwIOVectSignal(8)
        self.d = HwIOVectSignal(8)._m()

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        # inputs has to be readed to enter hls scope
        # (without read() operation will not be schedueled by HLS
        #  but they will be directly synthesized)
        a, b, c = [hls.read(hwIO).data for hwIO in [self.a, self.b, self.c]]
        # depending on target platform this expresion
        # can be mapped to DPS, LUT, etc...
        # no constrains are specified => default strategy is
        # to achieve zero delay and minimum latency, for this CLK_FREQ
        d = ~(~a & ~b) & ~c
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(d, self.d)
            ),
            self._name)
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
        dut = AlapAsapDiffExample()
        dut.CLK_FREQ = int(freq)
        a = 20
        b = 58
        c = 48
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.a._ag.data.append(a)
        dut.b._ag.data.append(b)
        dut.c._ag.data.append(c)

        self.runSim(int(40 * freq_to_period(dut.CLK_FREQ)))

        res = dut.d._ag.data[-1]
        self.assertValEqual(res, neg_8b(neg_8b(a) & neg_8b(b)) & neg_8b(c))


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = AlapAsapDiffExample()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AlapAsapDiffExample_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(AlapAsapDiffExample_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
