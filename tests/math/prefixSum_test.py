#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Callable

from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.architecture.componentGenerators.prefixSum import prefixSum1bPerResultBinTreeBased, \
    prefixSum1bFenwickTree, prefixSumNaivePy
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import get_bit
from tests.frontend.trivial import WriteOnce


class TestHwModulePrefixSum(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        self.ITEM_CNT = HwParam(8)
        self.FN = HwParam(prefixSum1bPerResultBinTreeBased)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        i = self.data_in = HwIOStructRdVld()
        i.T = BIT[self.ITEM_CNT]
        o = self.data_out = HwIOStructRdVld()._m()
        o.T = HBits(log2ceil(self.ITEM_CNT + 1), signed=False)[self.ITEM_CNT]

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            i = hls.read(self.data_in)
            o = self.FN(i.data)
            hls.write(HwIOArray(o), self.data_out)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class PrefixSumTC(SimTestCase):

    def tearDown(self):
        self.rmSim()
        SimTestCase.tearDown(self)

    def _test_py(self, fn: Callable[[list[HBitsConst]], list[HBitsConst]]):
        for i in range(0xff):
            inputPy = [get_bit(i, bitI) for bitI in range(8)]
            prefixSumRef = prefixSumNaivePy(inputPy)
            inputHbits = [b1 if b else b0 for b in inputPy]
            prefixSum = fn(inputHbits)
            self.assertValSequenceEqual(prefixSum, prefixSumRef)

    def _test_rtl(self, fn: Callable[[list[HBitsConst]], list[HBitsConst]]):
        dut = TestHwModulePrefixSum()
        dut.CLK_FREQ = int(1e6)
        dut.FN = fn
        # dut.OUT_CHANNEL_TYPE = dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        CLK_PERIOD = int(freq_to_period(dut.CLK_FREQ))
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        # dut.data_out._ag.presetBeforeClk = True
        # dut.data_in._ag.presetBeforeClk = True
        testTuple = tuple[int, int, int, int,
                          int, int, int, int, ]
        test_values: list[testTuple] = []
        ref: list[testTuple] = []
        for i in range(0xff):
            inputPy = tuple(get_bit(i, bitI) for bitI in range(8))
            test_values.append(inputPy)
            prefixSumRef = prefixSumNaivePy(inputPy)
            ref.append(tuple(prefixSumRef))

        dut.data_in._ag.data.extend(test_values)

        self.runSim((len(ref) + 3) * CLK_PERIOD)

        self.assertValSequenceEqual(dut.data_out._ag.data, ref)

    def test_prefixSum1bPerResultBinTreeBased_py(self):
        self._test_py(prefixSum1bPerResultBinTreeBased)

    def test_prefixSum1bFenwickTree_py(self):
        self._test_py(prefixSum1bFenwickTree)

    def test_prefixSum1bPerResultBinTreeBased_rtl(self):
        self._test_rtl(prefixSum1bPerResultBinTreeBased)

    def test_prefixSum1bFenwickTree_rtl(self):
        self._test_rtl(prefixSum1bFenwickTree)


if __name__ == '__main__':
    import sys
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(PrefixSumTC)
    # suite = unittest.TestSuite([PrefixSumTC('test_prefixSum1bPerResultBinTreeBased_rtl')])
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
