#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.io.bram.bramWrite import BramWrite
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC


class BramWrite_TC(SimTestCase):

    def test_BramWrite(self):
        u = BramWrite()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(u.CLK_FREQ))
        N = 8
        self.runSim((N + 1) * clkPeriod)
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        res = {i: int(v) for i, v in u.ram._ag.mem.items()}
        self.assertDictEqual({i: i for i in range(N)}, res)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BramWrite_TC("test_BramWrite")])
    suite = testLoader.loadTestsFromTestCase(BramWrite_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
