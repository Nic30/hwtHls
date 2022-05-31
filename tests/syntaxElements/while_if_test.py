#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC
from tests.syntaxElements.trivial_test import HlsStreamMachineTrivial_TC
from tests.syntaxElements.while_if import WhileAndIf0, WhileAndIf2, WhileAndIf3


class HlsStreamMachineWhileIf_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_WhileAndIf0_ll(self):
        self._test_ll(WhileAndIf0)

    def test_WhileAndIf0(self):
        u = WhileAndIf0()
        u.FREQ = int(10e6)
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK = 8
        clk_period = int(freq_to_period(u.FREQ))

        self.runSim((CLK + 1) * clk_period)
        HlsStreamMachineTrivial_TC._test_no_comb_loops(self)

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

        self.assertValSequenceEqual(u.dataOut._ag.data, expected)

    def test_WhileAndIf2(self, cls=WhileAndIf2):
        u = cls()
        u.FREQ = int(10e6)

        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        clk_period = freq_to_period(u.FREQ)
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

        u.dataIn._ag.data.extend(inputs)
        self.runSim((CLK + 10) * int(clk_period))
        HlsStreamMachineTrivial_TC._test_no_comb_loops(self)
        self.assertValSequenceEqual(u.dataOut._ag.data, expected)
    
    def test_WhileAndIf3(self):
        self.test_WhileAndIf2(WhileAndIf3)
    
    def test_WhileAndIf2_ll(self):
        self._test_ll(WhileAndIf2)

    def test_WhileAndIf4(self):
        raise NotImplementedError()


if __name__ == "__main__":
    import unittest
    # from hwt.synthesizer.utils import to_rtl_str
    # u = WhileAndIf0()
    # u.FREQ = int(10e6)
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))

    suite = unittest.TestSuite()
    # suite.addTest(HlsStreamMachineWhileIf_TC('test_WhileAndIf0'))
    suite.addTest(unittest.makeSuite(HlsStreamMachineWhileIf_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
