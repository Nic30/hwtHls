#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.bram.bramRead import BramReadWithRom
from hwtSimApi.utils import freq_to_period


class BramRead_TC(SimTestCase):

    def test_BramRead(self):
        u = BramReadWithRom()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        clkPeriod = int(freq_to_period(u.CLK_FREQ))
        # + 1 for reset, +1 for latency 
        self.runSim((32 + 1 + 1) * clkPeriod)
        HlsAstTrivial_TC._test_no_comb_loops(self)
        
        ref = []
        for _ in range(2):
            for i in range(16):
                ref.append(i + 1)
    
        self.assertValSequenceEqual(u.dataOut._ag.data, ref)


if __name__ == "__main__":
    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(BramRead_TC('test_ReadFsm1Once'))
    suite.addTest(unittest.makeSuite(BramRead_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
