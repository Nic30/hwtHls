#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from hwtHls.llvm.llvmIr import HFloatTmpSaturation, HFloatTmpRounding
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpUnary_TC, \
    FixpAdd_TC
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmpOps import sin, cos, sinpi, cospi, tan, sqrt, \
    atan2
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.fixp.cordicAtan2 import CordicAtan2


class FixpSinNoLut_TC(FixpUnary_TC):
    FP_TY = HFixedPointQ(4, 10, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    RTL_SIM_TIME_MULTIPLIER = 10
    MAX_TABLE_ADDR_WIDTH = 0
    defaultOptThroughputVsArea = 0.0
    INPUT_DATA = [
         0.0,
         0.1,
         0.2, 0.25, 0.5,
         1.0
    ]

    @staticmethod
    def HLS_OP_FN(a):
        return sin(a)

    def _model(self, a: float) -> float:
        return math.sin(a)


class FixpSinLut7_TC(FixpSinNoLut_TC):
    RTL_SIM_TIME_MULTIPLIER = 5
    MAX_TABLE_ADDR_WIDTH = 7


class FixpSinNoLutUnroll_TC(FixpSinNoLut_TC):
    defaultOptThroughputVsArea = 1.0


class FixpCosNoLut_TC(FixpSinNoLut_TC):

    @staticmethod
    def HLS_OP_FN(a):
        return cos(a)

    def _model(self, a: float) -> float:
        return math.cos(a)


class FixpCosLut7_TC(FixpCosNoLut_TC):
    RTL_SIM_TIME_MULTIPLIER = 5
    MAX_TABLE_ADDR_WIDTH = 7


class FixpCosNoLutUnroll_TC(FixpCosNoLut_TC):
    defaultOptThroughputVsArea = 1.0


class FixpTanNoLut_TC(FixpSinNoLut_TC):

    @staticmethod
    def HLS_OP_FN(a):
        return tan(a)

    def _model(self, a: float) -> float:
        return math.tan(a)


class FixpTanLut7_TC(FixpTanNoLut_TC):
    RTL_SIM_TIME_MULTIPLIER = 10
    MAX_TABLE_ADDR_WIDTH = 7


class FixpTanNoLutUnroll_TC(FixpTanNoLut_TC):
    defaultOptThroughputVsArea = 1.0


class FixpTanLut7Unroll_TC(FixpTanNoLut_TC):
    defaultOptThroughputVsArea = 1.0
    RTL_SIM_TIME_MULTIPLIER = 1.2
    MAX_TABLE_ADDR_WIDTH = 7


class FixpSinPiNoLut_TC(FixpSinNoLut_TC):

    @staticmethod
    def HLS_OP_FN(a):
        return sinpi(a)

    def _model(self, a: float) -> float:
        return math.sin(a * math.pi)


class FixpSinPiLut7_TC(FixpSinPiNoLut_TC):
    MAX_TABLE_ADDR_WIDTH = 7


class FixpSinPiNoLutUnroll_TC(FixpSinPiNoLut_TC):
    defaultOptThroughputVsArea = 1.0


class FixpCosPiNoLut_TC(FixpSinNoLut_TC):

    @staticmethod
    def HLS_OP_FN(a):
        return cospi(a)

    def _model(self, a: float) -> float:
        return math.cos(a * math.pi)


class FixpCosPiLut7_TC(FixpCosPiNoLut_TC):
    RTL_SIM_TIME_MULTIPLIER = 5
    MAX_TABLE_ADDR_WIDTH = 7


class FixpCosPiNoLutUnroll_TC(FixpCosPiNoLut_TC):
    defaultOptThroughputVsArea = 1.0


class FixpSqrt_TC(FixpSinNoLut_TC):
    FP_TY = HFixedPointQ(4, 20, signed=False, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    RTL_SIM_TIME_MULTIPLIER = 20.0

    @staticmethod
    def HLS_OP_FN(a):
        return sqrt(a)

    def _model(self, a: float) -> float:
        return math.sqrt(a)


class FixpSqrtUnroll_TC(FixpSqrt_TC):
    defaultOptThroughputVsArea = 1.0


class FixpSqrt_int_TC(FixpSqrt_TC):
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


class FixpAtan2_TC(FixpAdd_TC):
    FP_TY = HFixedPointQ(6, 8,
                         rounding=HFloatTmpRounding.ROUND_FLOOR,
                         saturation=HFloatTmpSaturation.SATURATE_NONE)
    ITERATION_COUNT = 12
    RTL_SIM_TIME_MULTIPLIER = 10.0

    # INPUT_DATA = [
    #    (0, 0.25),
    #    #(0.25, 0.25),
    # ]
    INPUT_DATA = [
        (0.0, 0.0),
        (0.0, 0.25),
        (0.25, 0.25),
        (1.0, 1.0),
        (0.1, 0.2),
        (0.1, 0.1),
        (0.123, 0.123),
        (0.123, 0.456),
        (1.125, 1.0),
        (1.25, 1.0),
        (1.0, 2.0),
        (1.0, 2.25),
        (2.0, 0.25),
        (-2.0, 0.25),
        (-1.0, -1.0),
        (10.0, 5.0),
        (5.0, 10.0),
    ]

    def _model(self, y:float, x:float) -> float:
        return math.atan2(y, x)

    def test_py(self):
        ty = HFloatTmp
        atan2 = CordicAtan2(self.ITERATION_COUNT)
        for _y, _x in self.INPUT_DATA:
            y = ty.from_py(_y)
            x = ty.from_py(_x)
            ref = self._model(y, x)
            res = atan2.atan2(y, x)
            resF = float(res[0])
            self.assertAlmostEqual(resF, ref, delta=2 ** -10, msg=(_y, _x))

    @staticmethod
    def HLS_OP_FN(y, x):
        return atan2(y, x)


class FixpAtan2Unroll_TC(FixpAtan2_TC):
    defaultOptThroughputVsArea = 1.0
    RTL_SIM_TIME_MULTIPLIER = 1.0


FixpOpTrigonometric_TCs = [
    FixpSinNoLutUnroll_TC,
    FixpCosNoLutUnroll_TC,
    FixpTanNoLutUnroll_TC,
    FixpSinPiNoLutUnroll_TC,
    FixpCosPiNoLutUnroll_TC,
    
    FixpSinNoLut_TC,
    FixpCosNoLut_TC,
    FixpTanNoLut_TC, # [fixme] tan does not recognize that sin/cos/div are not unrolled and 
                     #  _BaseALU1HwModule then incorerectly resolves sync
    FixpSinPiNoLut_TC,
    FixpCosPiNoLut_TC,
    
    FixpSinLut7_TC,
    FixpCosLut7_TC,
    FixpTanLut7_TC,
    FixpSinPiLut7_TC,
    FixpCosPiLut7_TC,
    
    FixpTanLut7Unroll_TC,
    
    FixpSqrt_TC,
    FixpSqrtUnroll_TC,
    FixpSqrt_int_TC,
    FixpAtan2_TC,
    FixpAtan2Unroll_TC,
]

if __name__ == "__main__":
    #from hwt.synth import to_rtl_str
    #from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    #from hwtHls.platform.xilinx.artix7 import Artix7Fast
    #from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
    #from tests.math.componentGenerators.install import installFpComponentGenerators
    #
    #m = _FixpUnOpTestModule()
    #m.FN = cospi
    #m.T = HFixedPointQ(4, 10, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    #m.CLK_FREQ = int(1e6)
    #platform = Artix7Fast(
    #   debugFilter=HlsDebugBundle.ALL_RELIABLE,
    #   #llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED, ]
    #)
    #installFpComponentGenerators(platform, defaultOptThroughputVsArea=1.0, MAX_TABLE_ADDR_WIDTH=0)
    #print(to_rtl_str(m, target_platform=platform))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpTanNoLutUnroll_TC('test_rtl')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpTrigonometric_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

