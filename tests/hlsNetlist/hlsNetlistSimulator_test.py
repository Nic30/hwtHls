#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.commonConstants import b0, b1
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import HlsDebugBundle
from pyMathBitPrecise.bit_utils import get_bit
from tests.frontend.ifstm_test import HlsSimpleIfStatement
from tests.frontend.whileTrue import WhileTrueWriteCntr0
from tests.io.ioFsm import WriteFsm0WhileTrue123
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule


class HlsNetlistSimulator_TC(SimTestCase):

    def test_HlsSimpleIfStatement(self):
        # :note: simple combinational 1 clk circuit with 3 inputs, 1 output and 1 mux
        dut = HlsSimpleIfStatement()
        # test all combinations
        a = []
        b = []
        c = []
        d = []
        for i in range(1 << 3):
            _a = get_bit(i, 0)
            _b = get_bit(i, 1)
            _c = get_bit(i, 2)
            a.append(b1 if _a else b0)
            b.append(b1 if _b else b0)
            c.append(b1 if _c else b0)
            _d = dut.model(_a, _b, _c)
            d.append(_d)

        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setRunTestsAfter(runTestAfterEachHlsNetlistPass=True)
        passTests.setTimeLimits(wallTimeRtl=(1 << 3) + 1)
        passTests.bindDataByInOut((a, b, c), (d,), PORT_NAMES=("a", "b", "c", "d"))
        passTests.test_allInOne()

    def test_WhileTrueWriteCntr0(self):
        # :note: simple circuit with adder and backedge
        dut = WhileTrueWriteCntr0()
        N = 10
        ref = list(range(N))

        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setRunTestsAfter(runTestAfterEachHlsNetlistPass=True)
        passTests.setTimeLimits(wallTimeRtl=N + 1)
        passTests.bindDataByInOut((), (ref,), OUT_ITEM_CNT_LIMITS=(N,), PORT_NAMES=("dataOut", ))
        passTests.test_allInOne()

    def test_WriteFsm0WhileTrue123(self):
        dut = WriteFsm0WhileTrue123()
        N = 10
        ref = list([(i % 3) + 1 for i in range(N)])

        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setRunTestsAfter(runTestAfterEachHlsNetlistPass=True)
        passTests.setTimeLimits(wallTimeRtl=N + 1)
        passTests.bindDataByInOut((), (ref,), OUT_ITEM_CNT_LIMITS=(N,), PORT_NAMES=("o", ))
        passTests.test_allInOne()


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HlsNetlistSimulator_TC)
    # suite = unittest.TestSuite([HlsNetlistSimulator_TC("test_HlsSimpleIfStatement")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
