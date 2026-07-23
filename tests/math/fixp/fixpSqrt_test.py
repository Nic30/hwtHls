#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.llvm.llvmIr import HFloatTmpSaturation, HFloatTmpRounding
from tests.math.componentGenerators.fsqrt import FixpSqrtHwModule
from tests.math.fixp._fixpAlu1_TC import FixpAlu1_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
from tests.math.fixp.fixpOperatorsTrigonometric_test import FixpSinNoLut_TC
from tests.math.fixp.fixpSqrt import fixpSqrt
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmpOps import sqrt
from hwt.pyUtils.typingFuture import override
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


@serializeParamsUniq
class TestModuleFixpSqrtGen(_FixpUnOpTestModule):

    @override
    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(data_in: float) -> float:
        return math.sqrt(data_in)

    @override
    @staticmethod
    def HLS_OP_FN(a):
        return sqrt(a)


class FixpSqrtGen_TC(FixpAlu1_TC):
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


class FixpSqrt_TC(FixpSqrtGen_TC):
    MODULE_CLS = FixpSqrtHwModule
    MAX_DELTA = 2.0 ** -20

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
        super().test_rtl(dut=dut, runTestAfterEachPass=runTestAfterEachPass)

    def test_py(self):
        fp = self.FP_TY.from_py
        model = self.MODULE_CLS.model
        for d in self.INPUT_DATA:
            resRef = model(d)
            _d = fp(d)
            res = fixpSqrt(_d)
            self.assertAlmostEqual(float(res), resRef, delta=self.MAX_DELTA)


class FixpSqrt_q2_10_TC(FixpSqrt_TC):
    MODULE_CLS = FixpSqrtHwModule
    FP_TY = HFixedPointQ(2, 10, signed=False,
                         rounding=HFloatTmpRounding.ROUND_FLOOR,
                         saturation=HFloatTmpSaturation.SATURATE_NONE)
    INPUT_DATA = [
        *FixpSinNoLut_TC.INPUT_DATA,
    ]
    MAX_DELTA = 2.0 ** -10


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
    FixpSqrtGen_TC,
    FixpSqrt_q2_10_TC,
    FixpSqrtUnroll_TC,
    FixpSqrt_int_TC,
]

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpSqrt_TCs])
    # suite = unittest.TestSuite([FixpSqrt_TC('test_py')])
    # suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(FixpSqrt_q2_10_TC)])

    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
