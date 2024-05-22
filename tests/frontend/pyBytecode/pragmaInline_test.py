#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.frontend.pyBytecode.pragmaInline import PragmaInline_singleBlock, \
    PragmaInline_NestedLoop, PragmaInline_return1_0, PragmaInline_return1_1, \
    PragmaInline_return1_1hw, PragmaInline_writeCntr0, PragmaInline_writeCntr1, \
    PragmaInline_writeCntr2, PragmaInline_writeCntr3, \
    PragmaInline_writeSaturatedCntr4, PragmaInline_SequenceCounter, \
    PragmaInline_FilterZeros, PragmaInline_TwoInLoopLiveVars
from tests.frontend.pyBytecode.varReference import \
    VarReference_writeCntr0, VarReference_writeCntr1


class PyBytecodeInline_TC(SimTestCase):

    def _test_writes1(self, hwModuleCls):
        dut = hwModuleCls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(int(100e6))
        self.runSim(3 * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o._ag.data, [1, 1, 1])

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

    def _test_writesCntr(self, hwModuleCls):
        dut = hwModuleCls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        self.runSim(4 * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o._ag.data, [0, 1, 2])

    def test_PragmaInline_writeCntr0(self):
        self._test_writesCntr(PragmaInline_writeCntr0)

    def test_PragmaInline_writeCntr1(self):
        self._test_writesCntr(PragmaInline_writeCntr1)

    def test_VarReference_writeCntr0(self):
        self._test_writesCntr(VarReference_writeCntr0)

    def test_VarReference_writeCntr1(self):
        self._test_writesCntr(VarReference_writeCntr1)

    def test_PragmaInline_writeCntr2(self):
        self._test_writesCntr(PragmaInline_writeCntr2)

    def test_PragmaInline_writeCntr3(self):
        self._test_writesCntr(PragmaInline_writeCntr3)

    def test_PragmaInline_writeSaturatedCntr4(self):
        self._test_writesCntr(PragmaInline_writeSaturatedCntr4)

    def test_PragmaInline_SequenceCounter(self):
        dut = PragmaInline_SequenceCounter()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.i._ag.data.extend([0, 0, 1, 0, 1, 1, 1, 0, 0, 0])

        def model(data):
            cntr = 0
            for d in data:
                if d == 0:
                    yield cntr
                    cntr = 0
                else:
                    cntr += 1

        ref = list(model(dut.i._ag.data))
        self.runSim((len(dut.i._ag.data) + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o._ag.data, ref)

    def test_PragmaInline_FilterZeros(self):
        dut = PragmaInline_FilterZeros()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.i._ag.data.extend([0, 0, 1, 0, 1, 1, 1, 0, 12, 0])

        def model(data):
            for d in data:
                if d != 0:
                    yield d

        ref = list(model(dut.i._ag.data))
        self.runSim((len(dut.i._ag.data) + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o._ag.data, ref)

    def test_PragmaInline_TwoInLoopLiveVars(self):
        dut = PragmaInline_TwoInLoopLiveVars()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.i._ag.data.extend([0, 0, 1, 0, 1, 129, 1, 1, 0, 12, 0])

        def model(data):
            it = iter(data)
            try:
                while True:
                    cntr = 0
                    v = next(it)
                    while v < 128:
                        cntr += v
                        v = next(it)
                    if v < 4:
                        cntr += 1
                    yield cntr
            except StopIteration:
                return

        ref = list(model(dut.i._ag.data))
        self.runSim((len(dut.i._ag.data) + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o._ag.data, ref)


if __name__ == "__main__":
    import unittest
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # m = PragmaInline_SequenceCounter()
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
    #     debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_20_addSignalNamesToSync,
    #                                                   HlsDebugBundle.DBG_20_addSignalNamesToData}))))
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PyBytecodeInline_TC("test_PragmaInline_SequenceCounter")])
    suite = testLoader.loadTestsFromTestCase(PyBytecodeInline_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
