#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.frontend.pyBytecode.pyArrShift import PyArrShift


class PyArrShift_TC(SimTestCase):

    def test_sequence(self):
        u = PyArrShift()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        u.i._ag.data.extend(range(1, 10))
        self.runSim(10 * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.o._ag.data, [0, 0, 1, 2, 3, 4, 5, 6, 7])


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(PyArrShift_TC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(PyArrShift_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)