#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random

from hwt.hdl.types.bits import HBits
from tests.math.componentGenerators._mul.mulSequential_test import PipelinedMultiplierSequential_4x4u_TC
from tests.math.componentGenerators._mul.mulToom2_5 import PipelinedMultiplierToom2_5
from tests.math.componentGenerators._mul.mulTestUtils import _ABContainer, \
    _testMulGenerateRandomTestValPairs


# partWidth 2
class PipelinedMultiplierToom2_6x4u_TC(PipelinedMultiplierSequential_4x4u_TC):
    RTL_SIM_TIME_MULTIPLIER = 1.0
    T = HBits(5 * 2, signed=False)
    T_LHS = HBits(3 * 2, signed=False)
    T_RHS = HBits(2 * 2, signed=False)
    INPUT_DATA = None

    @classmethod
    def setUpClass(cls) -> None:
        super(PipelinedMultiplierToom2_6x4u_TC, cls).setUpClass()
        N = 64
        rand = random.Random(0)
        cls.INPUT_DATA = _testMulGenerateRandomTestValPairs(rand, cls.T_LHS, cls.T_RHS, N)

    def prepareDataInFnRtl(self):
        T_LHS = self.T_LHS
        T_RHS = self.T_RHS
        for (a, b) in self.INPUT_DATA:
            a = T_LHS.from_py(a)
            b = T_RHS.from_py(b)
            yield (a, b)

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = PipelinedMultiplierToom2_5()
        dut.T = self.T
        dut.T_LHS = self.T_LHS
        dut.T_RHS = self.T_RHS
        dut.CLK_FREQ = freq
        self._test_rtl(dut, freq, runTestAfterEachPass)

    def test_py(self):
        dut = PipelinedMultiplierToom2_5()
        T0 = dut.T_LHS = self.T_LHS
        T1 = dut.T_RHS = self.T_RHS
        dut.T = self.T

        for a, b in self.INPUT_DATA:
            ref = self._model(a, b)
            inp = _ABContainer(T0.from_py(a), T1.from_py(b))
            res = dut.aluFn(inp, isSim=True)
            self.assertEqual(int(res), ref, (a, b))


class PipelinedMultiplierToom2_6x4s_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(5 * 2, signed=True)
    T_LHS = HBits(3 * 2, signed=True)
    T_RHS = HBits(2 * 2, signed=True)


# part widh 3
class PipelinedMultiplierToom2_9x6u_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(9 + 6, signed=False)
    T_LHS = HBits(9, signed=False)
    T_RHS = HBits(6, signed=False)


class PipelinedMultiplierToom2_9x6s_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(9 + 6, signed=True)
    T_LHS = HBits(9, signed=True)
    T_RHS = HBits(6, signed=True)


# part widh 4
class PipelinedMultiplierToom2_12x8u_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(12 + 8, signed=False)
    T_LHS = HBits(12, signed=False)
    T_RHS = HBits(8, signed=False)


class PipelinedMultiplierToom2_12x8s_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(12 + 8, signed=True)
    T_LHS = HBits(12, signed=True)
    T_RHS = HBits(8, signed=True)


# part widh 8
class PipelinedMultiplierToom2_24x16u_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(24 + 16, signed=False)
    T_LHS = HBits(24, signed=False)
    T_RHS = HBits(16, signed=False)


class PipelinedMultiplierToom2_24x16s_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(24 + 16, signed=True)
    T_LHS = HBits(24, signed=True)
    T_RHS = HBits(16, signed=True)


# part widh 32
class PipelinedMultiplierToom2_96x64u_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(96 + 64, signed=False)
    T_LHS = HBits(96, signed=False)
    T_RHS = HBits(64, signed=False)


class PipelinedMultiplierToom2_96x64s_TC(PipelinedMultiplierToom2_6x4u_TC):
    T = HBits(96 + 64, signed=True)
    T_LHS = HBits(96, signed=True)
    T_RHS = HBits(64, signed=True)


PipelinedMultiplierToom2_5_TCs = [
    PipelinedMultiplierToom2_6x4u_TC,
    PipelinedMultiplierToom2_6x4s_TC,
    PipelinedMultiplierToom2_9x6u_TC,
    PipelinedMultiplierToom2_9x6s_TC,
    PipelinedMultiplierToom2_12x8u_TC,
    PipelinedMultiplierToom2_12x8s_TC,
    PipelinedMultiplierToom2_24x16u_TC,
    PipelinedMultiplierToom2_24x16s_TC,
    PipelinedMultiplierToom2_96x64u_TC,
    PipelinedMultiplierToom2_96x64s_TC,
]

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PipelinedMultiplierToom2_6x4s_TC('test_rtl')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in PipelinedMultiplierToom2_5_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
