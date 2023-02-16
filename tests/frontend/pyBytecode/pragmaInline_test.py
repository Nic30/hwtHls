#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.frontend.pyBytecode.pragmaInline import PragmaInline_singleBlock, \
    PragmaInline_NestedLoop, PragmaInline_return1_0, PragmaInline_return1_1, \
    PragmaInline_return1_1hw, PragmaInline_writeCntr0, PragmaInline_writeCntr1, \
    PragmaInline_writeCntr2, PragmaInline_writeCntr3


class PyBytecodeInline_TC(SimTestCase):

    def _test_writes1(self, unitCls):
        u = unitCls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(int(100e6))
        self.runSim(3 * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.o._ag.data, [1, 1, 1])

    def test_PragmaInline_singleBlock(self):
        self._test_writes1(PragmaInline_singleBlock)

    def test_PragmaInline_NestedLoop(self):
        self._test_writes1(PragmaInline_NestedLoop)

    def test_PragmaInline_return1_0(self):
        self._test_writes1(PragmaInline_return1_0)

    def test_PragmaInline_return1_1(self):
        self._test_writes1(PragmaInline_return1_1)

    def test_PragmaInline_return1_1hw(self):
        self._test_writes1(PragmaInline_return1_1hw)

    def _test_writesCntr(self, unitCls):
        u = unitCls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        self.runSim(4 * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.o._ag.data, [0, 1, 2])

    def test_PragmaInline_writeCntr0(self):
        self._test_writesCntr(PragmaInline_writeCntr0)

    def test_PragmaInline_writeCntr1(self):
        self._test_writesCntr(PragmaInline_writeCntr1)

    def test_PragmaInline_writeCntr2(self):
        self._test_writesCntr(PragmaInline_writeCntr2)

    def test_PragmaInline_writeCntr3(self):
        self._test_writesCntr(PragmaInline_writeCntr3)


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = PragmaInline_writeCntr2()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    suite = unittest.TestSuite()
    #suite.addTest(PyBytecodeInline_TC('test_PragmaInline_writeCntr2'))
    suite.addTest(unittest.makeSuite(PyBytecodeInline_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
