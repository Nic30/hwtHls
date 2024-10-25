#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.ast.whileIf import WhileAndIf0, WhileAndIf2, WhileAndIf3, WhileAndIf4


class HlsAstWhileIf_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_WhileAndIf0_ll(self):
        self._test_ll(WhileAndIf0)

    def test_WhileAndIf0(self):
        dut = WhileAndIf0()
        dut.FREQ = int(10e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK = 8
        clk_period = int(freq_to_period(dut.FREQ))

        self.runSim((CLK + 1) * clk_period)
        BaseIrMirRtl_TC._test_no_comb_loops(self)

        expected = []

        def model():
            while True:
                x = 10
                while x:
                    if x < 3:
                        x = x - 1
                    else:
                        x = x - 3
                    yield x

        m = model()
        for _ in range(CLK):
            expected.append(next(m))

        self.assertValSequenceEqual(dut.dataOut._ag.data, expected)

    def test_WhileAndIf2(self, cls=WhileAndIf2):
        dut = cls()
        dut.FREQ = int(40e6)

        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        clk_period = freq_to_period(dut.FREQ)
        inputs = [6, 4, 0, 3, 3, 3, 1]
        CLK = len(inputs)
        expected = []
        in_iter = iter(inputs)
        clk_it = iter(range(CLK))
        try:
            while True:
                x = 10
                while x:
                    x = x - next(in_iter)
                    expected.append(x)
                    next(clk_it)
        except StopIteration:
            pass

        dut.dataIn._ag.data.extend(inputs)
        self.runSim((CLK + 10) * int(clk_period))
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        self.assertValSequenceEqual(dut.dataOut._ag.data, expected)

    def test_WhileAndIf3(self):
        self.test_WhileAndIf2(WhileAndIf3)

    def test_WhileAndIf2_ll(self):
        self._test_ll(WhileAndIf2)

    def test_WhileAndIf4(self):
        dut = WhileAndIf4()
        dut.FREQ = int(10e6)

        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        clk_period = freq_to_period(dut.FREQ)
        inputs = [6, 4, 0, 3, 3, 3, 1]
        CLK = len(inputs)
        expected = []
        in_iter = iter(inputs)
        clk_it = iter(range(CLK))
        try:
            while True:
                x = dut.dataOut.data._dtype.from_py(10)
                while True:
                    x = x - next(in_iter)
                    if x < 5:
                        expected.append(int(x))
                    next(clk_it)
        except StopIteration:
            pass

        dut.dataIn._ag.data.extend(inputs)
        self.runSim((CLK + 10) * int(clk_period))
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        self.assertValSequenceEqual(dut.dataOut._ag.data, expected)

    def test_WhileAndIf4_ll(self):
        self._test_ll(WhileAndIf4)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = WhileAndIf4()
    m.DATA_WIDTH = 4
    m.FREQ = int(40e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsAstWhileIf_TC('test_WhileAndIf0')])
    suite = testLoader.loadTestsFromTestCase(HlsAstWhileIf_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
