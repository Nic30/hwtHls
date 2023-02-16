#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.pyBytecode.readNonBlocking import HlsPythonReadNonBlocking


class ReadNonBlocking_TC(SimTestCase):

    def test_HlsPythonReadNonBlocking(self):
        u = HlsPythonReadNonBlocking()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.i._ag.data.extend(0 for _ in range(40))
        self.randomize(u.i)
        self.runSim(10 * CLK_PERIOD)
        self.assertValSequenceEqual(u.o._ag.data, [-1, 0, 1, 2, 1, 2, 3, 4, 3])


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(ReadNonBlocking_TC('test_HlsPythonReadNonBlocking'))
    suite.addTest(unittest.makeSuite(ReadNonBlocking_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
