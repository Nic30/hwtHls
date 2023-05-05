#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axiLite_comp.sim.ram import Axi4LiteSimRam
from hwtSimApi.utils import freq_to_period
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.amba.axi4Lite.axi4LiteWrite import Axi4LiteWrite


class Axi4LiteWrite_TC(SimTestCase):

    def test_Axi4LiteWrite(self):
        u = Axi4LiteWrite()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(u.CLK_FREQ))
        mem = Axi4LiteSimRam(u.ram)
        N = 8
        self.runSim((N + 2) * clkPeriod)
        HlsAstTrivial_TC._test_no_comb_loops(self)
        res = {i: int(v) for i, v in mem.data.items()}
        self.assertDictEqual({i: i for i in range(N)}, res)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4LiteWrite_TC("test_Axi4LiteWrite")])
    suite = testLoader.loadTestsFromTestCase(Axi4LiteWrite_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
