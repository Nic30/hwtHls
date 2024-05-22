#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.frontend.pyBytecode.pyArrShift import PyArrShift, PyArrShiftFn, PyArrShiftFnStruct


class PyArrShift_TC(SimTestCase):

    def test_sequence_PyArrShift(self, cls=PyArrShift):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.i._ag.data.extend(range(1, 10))
        self.runSim(10 * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o._ag.data, [0, 0, 1, 2, 3, 4, 5, 6, 7])

    def test_sequence_PyArrShiftInFn(self):
        self.test_sequence_PyArrShift(PyArrShiftFn)

    def test_sequence_PyArrShiftFnStruct(self):
        self.test_sequence_PyArrShift(PyArrShiftFnStruct)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PyArrShift_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(PyArrShift_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
