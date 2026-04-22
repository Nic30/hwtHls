#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from hwt.serializer.mode import serializeParamsUniq
from hwtHls.llvm.llvmIr import HFloatTmpSaturation, HFloatTmpRounding
from tests.math.fixp.cordicAtan2 import CordicAtan2
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpUnary_TC, \
    FixpAdd_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule, _FixpBinOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import sin, cos, sinpi, cospi, tan, atan2


@serializeParamsUniq
class TestModuleFixpSin(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return sin(a)


class FixpSinNoLut_TC(FixpUnary_TC):
    FP_TY = HFixedPointQ(4, 10, rounding=HFloatTmpRounding.ROUND_HALF_EVEN,
                                saturation=HFloatTmpSaturation.SATURATE_NONE)
    RTL_SIM_TIME_MULTIPLIER = 10
    MAX_TABLE_ADDR_WIDTH = 0
    optThroughputVsArea = 0.0
    # https://flop.evanau.dev/float-converter
    INPUT_DATA = [  # ============== fp32 ===============  == q4.10 ==
         0.0,  # 0 0000 0000 00000000000000000000000   0
         0.0146484375,  # 0 0111 1000 11100000000000000000000   15
         0.12890625,  # 0 0111 1100 00001000000000000000000   132
         # 0.1,
         0.1875,  # 0 0111 1100 10000000000000000000000   192
         0.21875,  # 0 0111 1100 11000000000000000000000   224
         0.25,  # 0 0111 1101 00000000000000000000000   256
         0.5,  # 0 0111 1110 00000000000000000000000   512
         0.9375,  # 0 0111 1110 11100000000000000000000   960
         1.0  # 0 0111 1111 00000000000000000000000   1024
    ]
    MODULE_CLS = TestModuleFixpSin

    def _model(self, a: float) -> float:
        return math.sin(a)


class FixpSinLut7_TC(FixpSinNoLut_TC):
    RTL_SIM_TIME_MULTIPLIER = 5
    MAX_TABLE_ADDR_WIDTH = 7


class FixpSinNoLutUnroll_TC(FixpSinNoLut_TC):
    optThroughputVsArea = 1.0


@serializeParamsUniq
class TestModuleFixpCos(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return cos(a)


class FixpCosNoLut_TC(FixpSinNoLut_TC):

    MODULE_CLS = TestModuleFixpCos

    def _model(self, a: float) -> float:
        return math.cos(a)


class FixpCosLut7_TC(FixpCosNoLut_TC):
    RTL_SIM_TIME_MULTIPLIER = 5
    MAX_TABLE_ADDR_WIDTH = 7


class FixpCosNoLutUnroll_TC(FixpCosNoLut_TC):
    optThroughputVsArea = 1.0


@serializeParamsUniq
class TestModuleFixpTan(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return tan(a)


class FixpTanNoLut_TC(FixpSinNoLut_TC):
    MODULE_CLS = TestModuleFixpTan
    RTL_SIM_TIME_MULTIPLIER = 64

    def _model(self, a: float) -> float:
        return math.tan(a)


class FixpTanLut7_TC(FixpTanNoLut_TC):
    RTL_SIM_TIME_MULTIPLIER = 10
    MAX_TABLE_ADDR_WIDTH = 7


class FixpTanNoLutUnroll_TC(FixpTanNoLut_TC):
    optThroughputVsArea = 1.0


class FixpTanLut7Unroll_TC(FixpTanNoLut_TC):
    optThroughputVsArea = 1.0
    RTL_SIM_TIME_MULTIPLIER = 1.2
    MAX_TABLE_ADDR_WIDTH = 7


@serializeParamsUniq
class TestModuleFixpSinpi(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return sinpi(a)


class FixpSinPiNoLut_TC(FixpSinNoLut_TC):

    MODULE_CLS = TestModuleFixpSinpi

    def _model(self, a: float) -> float:
        return math.sin(a * math.pi)


class FixpSinPiLut7_TC(FixpSinPiNoLut_TC):
    MAX_TABLE_ADDR_WIDTH = 7


class FixpSinPiNoLutUnroll_TC(FixpSinPiNoLut_TC):
    optThroughputVsArea = 1.0


@serializeParamsUniq
class TestModuleFixpCospi(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return cospi(a)


class FixpCosPiNoLut_TC(FixpSinNoLut_TC):

    MODULE_CLS = TestModuleFixpCospi

    def _model(self, a: float) -> float:
        return math.cos(a * math.pi)


class FixpCosPiLut7_TC(FixpCosPiNoLut_TC):
    RTL_SIM_TIME_MULTIPLIER = 5
    MAX_TABLE_ADDR_WIDTH = 7


class FixpCosPiNoLutUnroll_TC(FixpCosPiNoLut_TC):
    optThroughputVsArea = 1.0


@serializeParamsUniq
class TestModuleFixpAtan2(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(y, x):
        return atan2(y, x)


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
    MODULE_CLS = TestModuleFixpAtan2

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


class FixpAtan2Unroll_TC(FixpAtan2_TC):
    optThroughputVsArea = 1.0
    RTL_SIM_TIME_MULTIPLIER = 1.0


FixpOpTrigonometric_TCs = [
   FixpSinNoLutUnroll_TC,
   FixpCosNoLutUnroll_TC,
   FixpTanNoLutUnroll_TC,
   FixpSinPiNoLutUnroll_TC,
   FixpCosPiNoLutUnroll_TC,

   FixpSinNoLut_TC,
   FixpCosNoLut_TC,
   FixpTanNoLut_TC,
   FixpSinPiNoLut_TC,
   FixpCosPiNoLut_TC,

   FixpSinLut7_TC,
   FixpCosLut7_TC,
   FixpTanLut7_TC,
   FixpTanLut7Unroll_TC,
   FixpSinPiLut7_TC,
   FixpCosPiLut7_TC,

   FixpAtan2_TC,
   FixpAtan2Unroll_TC,
]

if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
    from tests.math.installMathLib import installMathLibComponentGenerators
    from hwt.serializer.verilog import VerilogSerializer

    m = _FixpUnOpTestModule()
    m.FN = sin
    m.T = HFixedPointQ(4, 10, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    m.CLK_FREQ = int(1e6)
    platform = Artix7Fast(
       debugFilter=HlsDebugBundle.ALL_RELIABLE,
       # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED, ]
    )
    installMathLibComponentGenerators(platform, optThroughputVsArea=0.0, MAX_TABLE_ADDR_WIDTH=0)
    # print(to_rtl_str(m, serializer_cls=VerilogSerializer, target_platform=platform))

    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpTrigonometric_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpSinNoLut_TC)
    # suite = unittest.TestSuite([FixpTanNoLut_TC('test_rtl')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

