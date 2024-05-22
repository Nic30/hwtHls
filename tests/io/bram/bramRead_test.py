#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.io.bram.bramRead import BramReadWithRom
from tests.io.bram.bramRead2R import BramRead2RWithRom


class BramRead_TC(SimTestCase):

    def test_BramRead(self):
        dut = BramReadWithRom()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(dut.CLK_FREQ))
        # + 1 for reset, +1 for latency
        self.runSim((32 + 1 + 1) * clkPeriod)
        BaseIrMirRtl_TC._test_no_comb_loops(self)

        ref = []
        for _ in range(2):
            for i in range(16):
                ref.append(i + 1)

        self.assertValSequenceEqual(dut.dataOut._ag.data, ref)

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
