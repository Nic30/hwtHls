#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.bram.bramWrite import BramWrite


class BramWrite_TC(SimTestCase):

    def test_BramWrite(self):
        u = BramWrite()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(u.CLK_FREQ))
        N = 8
        self.runSim((N + 1) * clkPeriod)
        HlsAstTrivial_TC._test_no_comb_loops(self)
        res = {i: int(v) for i, v in u.ram._ag.mem.items()}
        self.assertDictEqual({i: i for i in range(4)}, res)


if __name__ == "__main__":
    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(BramWrite_TC('test_BramWrite'))
    suite.addTest(unittest.makeSuite(BramWrite_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
