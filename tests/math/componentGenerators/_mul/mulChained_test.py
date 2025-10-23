#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import itertools
import random

from hwt.hdl.types.bits import HBits
from tests.math.componentGenerators._mul.mulChained import PipelinedMultiplierChained
from tests.math.componentGenerators._mul.mulSequential_test import PipelinedMultiplierSequential_4x4u_TC, \
    _allCombinationsOfValuesForBitewidthsForTy
from tests.math.componentGenerators._mul.mulTestUtils import _ABContainer, \
    _testMulGenerateRandomTestVals


class PipelinedMultiplierChained_4x4u_TC(PipelinedMultiplierSequential_4x4u_TC):
    T = HBits(4, signed=False)
    RTL_SIM_TIME_MULTIPLIER = 1.0
    MAX_MUL_OP_WIDTH = 2
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = PipelinedMultiplierChained()
        dut.MAX_MUL_RHS_WIDTH = self.MAX_MUL_OP_WIDTH
        dut.MAX_MUL_LHS_WIDTH = self.MAX_MUL_OP_WIDTH
        dut.T = self.T
        dut.CLK_FREQ = freq
        self._test_rtl(dut, freq, runTestAfterEachPass)

    def test_py(self):
        dut = PipelinedMultiplierChained()
        dut.MAX_MUL_RHS_WIDTH = self.MAX_MUL_OP_WIDTH
        dut.MAX_MUL_LHS_WIDTH = self.MAX_MUL_OP_WIDTH
        T = self.T
        dut.T = T

        for a, b in self.INPUT_DATA:
            ref = self._model(a, b)
            inp = _ABContainer(T.from_py(a), T.from_py(b))
            res = dut.aluFn(inp, isSim=True)
            self.assertEqual(int(res), ref, (a, b))


class PipelinedMultiplierChained_4x4s_TC(PipelinedMultiplierChained_4x4u_TC):
    T = HBits(4, signed=True)
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


class PipelinedMultiplierChained_6x6u_2_TC(PipelinedMultiplierChained_4x4u_TC):
    T = HBits(6, signed=False)
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


class PipelinedMultiplierChained_6x6s_2_TC(PipelinedMultiplierChained_4x4u_TC):
    T = HBits(6, signed=True)
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


class PipelinedMultiplierChained_6x6s_3_TC(PipelinedMultiplierChained_6x6s_2_TC):
    MAX_MUL_OP_WIDTH = 3


class PipelinedMultiplierChained_16x16u_32b_res_TC(PipelinedMultiplierChained_6x6s_2_TC):
    MAX_MUL_OP_WIDTH = 16
    T = HBits(32, signed=False)
    INPUT_DATA_1D = _testMulGenerateRandomTestVals(random.Random(0), T.signed, T.bit_length(), 64)
    INPUT_DATA = list(itertools.product(INPUT_DATA_1D, INPUT_DATA_1D))


class PipelinedMultiplierChained_16x16s_32b_res_TC(PipelinedMultiplierChained_6x6s_2_TC):
    MAX_MUL_OP_WIDTH = 16
    T = HBits(32, signed=True)
    INPUT_DATA_1D = _testMulGenerateRandomTestVals(random.Random(0), T.signed, T.bit_length(), 64)
    INPUT_DATA = list(itertools.product(INPUT_DATA_1D, INPUT_DATA_1D))


PipelinedMultiplierChained_TCs = [
    PipelinedMultiplierChained_4x4u_TC,
    PipelinedMultiplierChained_4x4s_TC,
    PipelinedMultiplierChained_6x6u_2_TC,
    PipelinedMultiplierChained_6x6s_2_TC,
    PipelinedMultiplierChained_6x6s_3_TC,
    PipelinedMultiplierChained_16x16u_32b_res_TC,
    PipelinedMultiplierChained_16x16s_32b_res_TC,
]

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PipelinedMultiplierChained_4x4u_TC('test_rtl')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in PipelinedMultiplierChained_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
