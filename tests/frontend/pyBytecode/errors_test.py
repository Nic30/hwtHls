#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.errors import HlsSyntaxError
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.frontend.pyBytecode.errors import ErrorUseOfUnitialized0, ErrorUseOfUnitialized1, UseOfNone


class PyBytecodeErrors_TC(SimTestCase):
    __FILE__ = __file__

    def _testEndsWithErr(self, unitCls, errCls):
        with self.assertRaises(errCls):
            self.compileSimAndStart(unitCls(), target_platform=VirtualHlsPlatform())
        
    def test_ErrorUseOfUnitialized0(self):
        self._testEndsWithErr(ErrorUseOfUnitialized0, HlsSyntaxError)

    def test_ErrorUseOfUnitialized1(self):
        self._testEndsWithErr(ErrorUseOfUnitialized1, HlsSyntaxError)
    
    def test_UseOfNone(self):
        u = UseOfNone()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(int(100e6))
        self.runSim(3 * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.o._ag.data, [1, 1, 1])


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PyBytecodeErrors_TC("test_ErrorUseOfUnitialized0")])
    suite = testLoader.loadTestsFromTestCase(PyBytecodeErrors_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
