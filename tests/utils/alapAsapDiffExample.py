#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwt.hdl.commonConstants import b1
from tests.frontend.ast.trivial import WriteOnce


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
    
    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        while b1:
            # inputs has to be read to enter hls scope
            # (without read() operation will not be scheduled by HLS
            #  but they will be directly synthesized)
            a, b, c = [hls.read(hwIO).data for hwIO in [self.a, self.b, self.c]]
            # depending on target platform this expression
            # can be mapped to DPS, LUT, etc...
            # no constrains are specified => default strategy is
            # to achieve zero delay and minimum latency, for this CLK_FREQ
            d = ~(~a & ~b) & ~c
            hls.write(d, self.d)

    @override
    def hwImpl(self):
        WriteOnce.hwImpl(self)


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
    from hwtHls.platform.debugBundle import HlsDebugBundle
    
    m = AlapAsapDiffExample()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AlapAsapDiffExample_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(AlapAsapDiffExample_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
