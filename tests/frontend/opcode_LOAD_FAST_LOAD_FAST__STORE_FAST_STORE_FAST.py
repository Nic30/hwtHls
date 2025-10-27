#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hwIOs.std import HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.trivial import WriteOnce


class TestOpcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.o = HwIOSignal()._m()

    def check(self, start, end):
        assert start == 1, (start, end)
        assert end == 2, (start, end)

    def mainThread(self, hls: HlsScope):
        while b1:
            start, end = 1, 2
            self.check(start, end)
            hls.write(0, self.o)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class TestOpcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST_TC(BaseSsaTC):
    __FILE__ = __file__
    TEST_MIR = False
    TEST_BLOCK_SYNC = False

    def test_toLlvm(self):
        dut = TestOpcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = TestOpcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([TestOpcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST_TC('test_simple')])
    suite = testLoader.loadTestsFromTestCase(TestOpcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
