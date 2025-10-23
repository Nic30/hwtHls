#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from tests.math.componentGenerators._mul.mulSequential_test import PipelinedMultiplierSequential_4x4u_TC, \
    _allCombinationsOfValuesForBitewidthsForTy
from tests.math.componentGenerators._mul.mulToom2 import PipelinedMultiplierToom2
from tests.math.componentGenerators._mul.mulChained_test import _ABContainer


class PipelinedMultiplierToom2_4x4u_2_TC(PipelinedMultiplierSequential_4x4u_TC):
    RTL_SIM_TIME_MULTIPLIER = 1.0
    MAX_MUL_OP_WIDTH = 2
    T = HBits(4, signed=False)
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]
    
    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = PipelinedMultiplierToom2()
        dut.T = self.T
        dut.MAX_MUL_LHS_WIDTH = dut.MAX_MUL_RHS_WIDTH = self.MAX_MUL_OP_WIDTH
        dut.CLK_FREQ = freq
        self._test_rtl(dut, freq, runTestAfterEachPass)
    
    def test_py(self):
        dut = PipelinedMultiplierToom2()
        dut.MAX_MUL_RHS_WIDTH = self.MAX_MUL_OP_WIDTH
        dut.MAX_MUL_LHS_WIDTH = self.MAX_MUL_OP_WIDTH
        T = self.T
        dut.T = T

        for a, b in self.INPUT_DATA:
            ref = self._model(a, b)
            inp = _ABContainer(T.from_py(a), T.from_py(b))
            res = dut.aluFn(inp, isSim=True)
            self.assertEqual(int(res), ref, (a, b))


class PipelinedMultiplierToom2_4x4s_2_TC(PipelinedMultiplierToom2_4x4u_2_TC):
    T = HBits(4, signed=True)
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


class PipelinedMultiplierToom2_6x6u_2_TC(PipelinedMultiplierToom2_4x4u_2_TC):
    T = HBits(6, signed=False)
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


class PipelinedMultiplierToom2_6x6s_2_TC(PipelinedMultiplierToom2_4x4u_2_TC):
    T = HBits(6, signed=True)
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


class PipelinedMultiplierToom2_6x6u_3_TC(PipelinedMultiplierToom2_6x6u_2_TC):
    MAX_MUL_OP_WIDTH = 3


class PipelinedMultiplierToom2_6x6s_3_TC(PipelinedMultiplierToom2_6x6s_2_TC):
    MAX_MUL_OP_WIDTH = 3


PipelinedMultiplierToom2_TCs = [
    PipelinedMultiplierToom2_4x4u_2_TC,
    PipelinedMultiplierToom2_4x4s_2_TC,
    PipelinedMultiplierToom2_6x6u_2_TC,
    PipelinedMultiplierToom2_6x6s_2_TC,
    PipelinedMultiplierToom2_6x6u_3_TC,
    PipelinedMultiplierToom2_6x6s_3_TC,
]

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    #suite = unittest.TestSuite([PipelinedMultiplierToom2_6x6u_2_TC('test_py')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in PipelinedMultiplierToom2_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
