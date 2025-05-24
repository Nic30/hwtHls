#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixpOperatorsHwModules import _FixpCastOpTestModule
from tests.math.fixp.fixpResize import fixp_resize, fixp_resize_py
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpAdd_TC, \
    FixpUnary_TC


class FixpResizeRoundHalfEvenSaturateSigned_3_2_to_3_1_TC(FixpUnary_TC):
    FP_TY = HFixedPointQ(3, 2)
    FP_TY_OUT = HFixedPointQ(3, 1)
    RTL_SIM_TIME_MULTIPLIER = 1.0
    INPUT_DATA = [
        0.0,
        0.25,
        0.5, 0.75, 1.25, 1.5, 1.75,
        -0.25, -0.5, -0.75, -1.25, -1.5,
    ]

    def HLS_OP_FN(self, a):
        return fixp_resize(a, self.FP_TY, self.FP_TY_OUT)

    def _model(self, a: float) -> float:
        FP_TY = self.FP_TY
        FP_TY_OUT = self.FP_TY_OUT
        res = fixp_resize_py(a, FP_TY_OUT.signed, FP_TY.int_bit_length, FP_TY.frac_bit_length,
                             FP_TY_OUT.int_bit_length, FP_TY_OUT.frac_bit_length,
                             FP_TY_OUT.rounding, FP_TY_OUT.saturation)
        return res

    def getCheckDataOutFn(self, REF_DATA):
        return FixpAdd_TC.getCheckDataOutFn(self, REF_DATA, fpTy=self.FP_TY_OUT)

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = _FixpCastOpTestModule()
        dut.T = self.FP_TY
        dut.T_OUT = self.FP_TY_OUT
        dut.CLK_FREQ = freq
        dut.FN = self.HLS_OP_FN
        FixpUnary_TC._test_rtl(self, dut, runTestAfterEachPass)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpDiv_TC('test_div_py')])
    suite = testLoader.loadTestsFromTestCase(FixpResizeRoundHalfEvenSaturateSigned_3_2_to_3_1_TC)
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

