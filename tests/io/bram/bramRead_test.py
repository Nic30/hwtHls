#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.io.bram.bramRead import BramReadWithRom
from tests.io.bram.bramRead2R import BramRead2RWithRom
from pyMathBitPrecise.bit_utils import mask


class BramRead_TC(SimTestCase):

    def _test_BramRead(self, DATA_WIDTH:int):
        dut = BramReadWithRom()
        dut.DATA_WIDTH = DATA_WIDTH
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(dut.CLK_FREQ))
        # + 1 for reset, +1 for latency
        self.runSim((32 + 1 + 1) * clkPeriod)
        BaseIrMirRtl_TC._test_no_comb_loops(self)

        maxVal = mask(DATA_WIDTH) + 1
        ref = []
        for _ in range(2):
            for i in range(16):
                ref.append((i + 1) % maxVal)

        self.assertValSequenceEqual(dut.dataOut._ag.data, ref)

    def test_BramRead_4096(self):
        self._test_BramRead(4096)

    def test_BramRead_128(self):
        self._test_BramRead(128)

    def test_BramRead_64(self):
        self._test_BramRead(64)

    def test_BramRead_36(self):
        self._test_BramRead(36)

    def test_BramRead_8(self):
        self._test_BramRead(8)

    def test_BramRead_4(self):
        self._test_BramRead(4)

    def test_BramRead_1(self):
        self._test_BramRead(1)

    def test_BramRead2R(self):
        dut = BramRead2RWithRom()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(dut.CLK_FREQ))
        # + 1 for reset, +1 for latency
        self.runSim((16 + 1 + 1) * clkPeriod)
        BaseIrMirRtl_TC._test_no_comb_loops(self)

        ref0 = []
        ref1 = []
        for _ in range(2):
            for i in range(8):
                ref0.append(i + 1)
            for i in range(8, 16):
                ref1.append(i + 1)

        self.assertValSequenceEqual(dut.dataOut0._ag.data, ref0)
        self.assertValSequenceEqual(dut.dataOut1._ag.data, ref1)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BramRead_TC("test_ReadFsm1Once")])
    suite = testLoader.loadTestsFromTestCase(BramRead_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
