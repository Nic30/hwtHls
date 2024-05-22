#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.pyBytecode.readNonBlocking import HlsPythonReadNonBlocking


class ReadNonBlocking_TC(SimTestCase):

    def test_HlsPythonReadNonBlocking(self):
        dut = HlsPythonReadNonBlocking()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.i._ag.data.extend(0 for _ in range(40))
        self.randomize(dut.i)
        self.runSim(10 * CLK_PERIOD)
        self.assertValSequenceEqual(dut.o._ag.data, [-1, 0, 1, 2, 1, 2, 3, 4, 3])


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ReadNonBlocking_TC("test_HlsPythonReadNonBlocking")])
    suite = testLoader.loadTestsFromTestCase(ReadNonBlocking_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
