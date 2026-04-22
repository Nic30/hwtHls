#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.llvm.llvmIr import HFloatTmpSaturation, HFloatTmpRounding
from tests.math.componentGenerators.fsqrt import FixpSqrtHwModule
from tests.math.fixp._fixpUnary_TC import FixpUnary_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
from tests.math.fixp.fixpOperatorsTrigonometric_test import FixpSinNoLut_TC
from tests.math.fixp.fixpSqrt import fixpSqrt
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmpOps import sqrt


@serializeParamsUniq
class TestModuleFixpSqrtGen(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return sqrt(a)


class FixpSqrtGen_TC(FixpUnary_TC):
    FP_TY = HFixedPointQ(4, 20, signed=False,
                         rounding=HFloatTmpRounding.ROUND_FLOOR,
                         saturation=HFloatTmpSaturation.SATURATE_NONE)
    RTL_SIM_TIME_MULTIPLIER = 22.0
    MODULE_CLS = TestModuleFixpSqrtGen
    INPUT_DATA = [
        *FixpSinNoLut_TC.INPUT_DATA,
        2.0,
        2.5,
        3.,
        4.0,
        4.25
    ]

    def _model(self, a: float) -> float:
        return math.sqrt(a)


class FixpSqrt_TC(FixpSqrtGen_TC):
    MODULE_CLS = FixpSqrtHwModule

    def prepareDataInFnRtl(self):
        fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())
        for a in self.INPUT_DATA:
            a = fpTy.from_py(a)._reinterpret_cast(bitTy)
            yield a

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = self.MODULE_CLS()
        dut.T = self.FP_TY
        dut.CLK_FREQ = freq
        dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        dut.OUT_CHANNEL_TYPE = HwIOStructRdVld
        self._test_rtl(dut, runTestAfterEachPass)

    def test_py(self):
        fp = self.FP_TY.from_py
        for d in self.INPUT_DATA:
            resRef = self._model(d)
            _d = fp(d)
            res = fixpSqrt(_d)
            self.assertAlmostEqual(float(res), resRef, delta=2.0 ** -20)


class FixpSqrtUnroll_TC(FixpSqrt_TC):
    optThroughputVsArea = 1.0


class FixpSqrt_int_TC(FixpSqrtGen_TC):
    FP_TY = HFixedPointQ(8, 0, signed=False,
                         rounding=HFloatTmpRounding.ROUND_FLOOR,
                         saturation=HFloatTmpSaturation.SATURATE_NONE)
    INPUT_DATA = [
         0.0,
         1.0,
         2.0,
         3.0,
         4.0,
         7.0,
         8.0,
        12.0,
        15.0,
    ]


FixpOpSqrt_TCs = [
    FixpSqrt_TC,
    FixpSqrtGen_TC,  # [fixme] the loop is not mapped into a single FSM and the pipeline sync is somehow broken
    FixpSqrtUnroll_TC,
    FixpSqrt_int_TC,
]

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpSqrt_TCs])
    # suite = unittest.TestSuite([FixpSqrt_TC('test_py')])
    # suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(FixpSqrt_TC)])

    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
