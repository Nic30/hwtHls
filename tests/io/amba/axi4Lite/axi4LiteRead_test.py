#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axiLite_comp.sim.ram import Axi4LiteSimRam
from hwtSimApi.utils import freq_to_period
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.amba.axi4Lite.axi4LiteRead import Axi4LiteRead


class Axi4LiteRead_TC(SimTestCase):

    def test_Axi4LiteRead(self):
        u = Axi4LiteRead()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        m = Axi4LiteSimRam(u.ram)
        t = u.ram.r.data._dtype
        N = 8
        for i in range(N):
            m.data[i] = t.from_py(i)

        clkPeriod = int(freq_to_period(u.CLK_FREQ))
        self.runSim((N + 2) * clkPeriod)
        HlsAstTrivial_TC._test_no_comb_loops(self)

        ref = []
        for i in range(N):
            ref.append(i)

        self.assertValSequenceEqual(u.dataOut._ag.data, ref)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4LiteRead_TC("test_Axi4LiteRead")])
    suite = testLoader.loadTestsFromTestCase(Axi4LiteRead_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
