#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.io.bram.bramWrite import BramWrite


class BramWrite_TC(SimTestCase):

    def _test_BramWrite(self, DATA_WIDTH:int, N:int=8):
        dut = BramWrite()
        dut.DATA_WIDTH = DATA_WIDTH
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(dut.CLK_FREQ))
        self.runSim((N + 1) * clkPeriod)
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        maxVal = mask(DATA_WIDTH) + 1
        res = {i: int(v) for i, v in dut.ram._ag.mem.items()}
        self.assertDictEqual(res, {i: i % maxVal for i in range(N)})

    def test_BramWrite_4096(self):
        self._test_BramWrite(4096)

    def test_BramWrite_128(self):
        self._test_BramWrite(128)

    def test_BramWrite_64(self):
        self._test_BramWrite(64)

    def test_BramWrite_36(self):
        self._test_BramWrite(36)

    def test_BramWrite_8(self):
        self._test_BramWrite(8)

    def test_BramWrite_4(self):
        self._test_BramWrite(4)

    def test_BramWrite_1(self):
        self._test_BramWrite(1)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BramWrite_TC("test_BramWrite")])
    suite = testLoader.loadTestsFromTestCase(BramWrite_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
