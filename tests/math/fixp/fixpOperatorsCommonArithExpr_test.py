#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.serializer.mode import serializeParamsUniq
from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp._fixpAlu1_TC import FixpAlu1_TC


@serializeParamsUniq
class TestModuleFixpDiv2(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a: float):
        return a / 2


class FixpDiv2_TC(FixpAlu1_TC):
    INPUT_DATA = [
        -3, -2, -1, 0, 1, 2, 3, 4, 5
    ]
    MODULE_CLS = TestModuleFixpDiv2

    def testRtl(self):
        self._test_rtl()


@serializeParamsUniq
class TestModuleFixpDiv_m2(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return a / -2


class FixpDiv_m2_TC(FixpDiv2_TC):
    MODULE_CLS = TestModuleFixpDiv_m2


@serializeParamsUniq
class TestModuleFixpDiv4(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return a / 4


class FixpDiv4_TC(FixpDiv2_TC):
    MODULE_CLS = TestModuleFixpDiv4


@serializeParamsUniq
class TestModuleFixpDiv_m4(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return a / -4


class FixpDiv_m4_TC(FixpDiv2_TC):
    MODULE_CLS = TestModuleFixpDiv_m4


@serializeParamsUniq
class TestModuleFixpDiv_0_5(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return a / 0.5


class FixpDiv_0_5_TC(FixpDiv2_TC):
    FP_TY = HFixedPointQ(5, 8)
    MODULE_CLS = TestModuleFixpDiv_0_5


@serializeParamsUniq
class TestModuleFixpDiv_m0_5(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return a / -0.5


class FixpDiv_m0_5_TC(FixpDiv2_TC):
    FP_TY = HFixedPointQ(5, 8)
    MODULE_CLS = TestModuleFixpDiv_m0_5


FixpOpCommonArithExpr_TCs = [
    FixpDiv2_TC,
    FixpDiv4_TC,
    FixpDiv_0_5_TC,
    FixpDiv_m2_TC,
    FixpDiv_m4_TC,
    FixpDiv_m0_5_TC,
]

# [todo]
#   x* c where c is constant and has few 1 bits to add
#   x*-1 to -x
#   0-x to -x

if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast

    # m = _FixpBinOpTestModule()
    # m.FN = lambda a, b: a * b
    # # m = _FixpUnOpTestModule()
    # # m.FN = lambda a: sin(a)
    # # m.T = HFixedPointQ(4, 8)
    # # m = _FixpCastOpTestModule()
    # m.CLK_FREQ = int(1e6)
    # platform = Artix7Fast(
    #    debugFilter=HlsDebugBundle.ALL_RELIABLE,
    #    # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL, ]
    # )
    # installFpComponentGenerators(platform)
    # print(to_rtl_str(m, target_platform=platform))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpDiv_TC('test_div_py')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpCommonArithExpr_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
