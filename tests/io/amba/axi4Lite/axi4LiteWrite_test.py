#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axiLite_comp.sim.ram import Axi4LiteSimRam
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.io.amba.axi4Lite.axi4LiteWrite import Axi4LiteWrite


class Axi4LiteWrite_TC(SimTestCase):

    def test_Axi4LiteWrite(self):
        dut = Axi4LiteWrite()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(dut.CLK_FREQ))
        mem = Axi4LiteSimRam(dut.ram)
        N = 8
        self.runSim((N + 2) * clkPeriod)
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        res = {i: int(v) for i, v in mem.data.items()}
        self.assertDictEqual({i: i for i in range(N)}, res)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4LiteWrite_TC("test_Axi4LiteWrite")])
    suite = testLoader.loadTestsFromTestCase(Axi4LiteWrite_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
