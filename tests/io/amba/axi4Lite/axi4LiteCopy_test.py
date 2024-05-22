#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axiLite_comp.sim.ram import Axi4LiteSimRam
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.io.amba.axi4Lite.axi4LiteCopy import Axi4LiteCopy


class Axi4LiteCopy_TC(SimTestCase):

    def test_Axi4LiteCopy(self):
        dut = Axi4LiteCopy()
        WORD_SIZE = 8
        dut.ADDR_WIDTH = 5 + 3
        dut.OFFSET = 16 * WORD_SIZE
        dut.DATA_WIDTH = WORD_SIZE * 8
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        m = Axi4LiteSimRam(dut.ram)
        t = dut.ram.r.data._dtype
        N = 8
        MAGIC = 0x10
        ref = []
        for i in range(N):
            m.data[i] = t.from_py(i + MAGIC)
            ref.append(i + MAGIC)

        clkPeriod = int(freq_to_period(dut.CLK_FREQ))
        self.runSim((3 * N + 1) * clkPeriod)
        BaseIrMirRtl_TC._test_no_comb_loops(self)

        inRamData = m.getArray(dut.OFFSET, WORD_SIZE, N)
        self.assertValSequenceEqual(inRamData, ref)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4LiteCopy_TC("test_Axi4LiteRead")])
    suite = testLoader.loadTestsFromTestCase(Axi4LiteCopy_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
