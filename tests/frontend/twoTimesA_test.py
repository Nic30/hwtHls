#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.constants import Time
from hwt.hdl.commonConstants import b1
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.trivial import WriteOnce


class TwoTimesA0(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = int(100e6)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.a = HwIOVectSignal(8)
        self.b = HwIOVectSignal(8)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            a = hls.read(self.a).data
            hls.write(a + a, self.b)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class TwoTimesA1(TwoTimesA0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            a = hls.read(self.a).data
            b = a + a
            hls.write(b, self.b)


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
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = TwoTimesA1()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([TwoTimesA_TC('test_TwoTimesA0')])
    suite = testLoader.loadTestsFromTestCase(TwoTimesA_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
