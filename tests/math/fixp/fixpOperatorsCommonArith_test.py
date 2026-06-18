#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
from pyMathBitPrecise.bit_utils import mask, to_signed
from tests.math.fixp._fixpAlu2_TC import FixpAlu2_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpBinOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixpdivrem import fixpDivremRestoring, FixpDivRemHwModule
from tests.math.fixp.passTestIoFixp import PassTestIoOutStructHFixedPoint2


@serializeParamsUniq
class TestModuleFixpAdd(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a + b


class FixpAdd_TC(FixpAlu2_TC):
    FP_TY = HFixedPointQ(4, 8)
    MAX_TABLE_ADDR_WIDTH = 0
    optThroughputVsArea = 0.0
    RTL_SIM_TIME_MULTIPLIER = 1.0
    INPUT_DATA = [
        (0.0, 0.0),
        (0.0, 0.25),
        (0.25, 0.25),
        (1.0, 1.0),
        (1.125, 1.0),
        (1.25, 1.0),
        (1.0, 2.0),
        (1.0, 2.25),
        (2.0, 0.25),
        (-2.0, 0.25),
        (-1.0, -1.0),
    ]
    MODULE_CLS = TestModuleFixpAdd
    MAX_ULP = 0


@serializeParamsUniq
class TestModuleFixpSub(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a - b


class FixpSub_TC(FixpAdd_TC):
    MODULE_CLS = TestModuleFixpSub


@serializeParamsUniq
class TestModuleFixpMul(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a * b


class FixpMul_TC(FixpAdd_TC):
    MODULE_CLS = TestModuleFixpMul


@serializeParamsUniq
class _TestModuleFixpDiv(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a / b


class FixpDiv_TC(FixpAlu2_TC):
    RTL_SIM_TIME_MULTIPLIER = FixpAdd_TC.FP_TY.bit_length() + FixpAdd_TC.FP_TY.frac_bit_length + 1
    INPUT_DATA = [
       (0.0, 0.25),
       (1.0, 1.0),
       (2.0, 1.0),
       (2.0, 2.0),
       (1.0, 0.5),
       (1.0, 0.25),
       (0.25, 0.25),
       (1.5, 1.0),
       (1.25, 1.0),
       (1.125, 1.0),
       (1.0, 2.0),
       (1.0, 2.25),
       (2.0, 0.5),
       (-2.0, 0.25),
       (-1.0, -1.0),
    ]

    MODULE_CLS = _TestModuleFixpDiv

    def test_py(self):
        fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())

        def toFloat(v: HBitsConst):
            if v._is_full_valid():
                return float(bitTy.from_py(v.val, v.vld_mask)._reinterpret_cast(fpTy)) if v._is_full_valid() else v
            else:
                return None

        def toBitVecFloat(v: float):
            return fpTy.from_py(v)._reinterpret_cast(bitTy)

        isSigned = bool(fpTy.signed)
        for (dividend, divisor) in self.INPUT_DATA:
            _dividend = toBitVecFloat(dividend)
            _divisor = toBitVecFloat(divisor)
            quotient = dividend / divisor
            remainder = math.fmod(dividend, divisor)
            _quotient, _remainder, overflow = fixpDivremRestoring(fpTy, _dividend, _divisor, isSigned,
                                                                  loopPragmaGetter=lambda: None, dbgNoSplitSlices=False)
            msg = (
                (dividend, "/", divisor, "==", (quotient, remainder), (int(toBitVecFloat(quotient)), int(toBitVecFloat(remainder)))),
                ("res:", (toFloat(_quotient), toFloat(_remainder)), (_quotient, _remainder))
            )
            self.assertAlmostEqual(toFloat(_quotient), quotient, msg=msg, delta=0.001)
            self.assertAlmostEqual(toFloat(_remainder), remainder, msg=msg, delta=0.001)


class FixpDivUnroll_TC(FixpDiv_TC):
    optThroughputVsArea = 1.0


class FixpDiv_q1_8_TC(FixpDivUnroll_TC):
    FP_TY = HFixedPointQ(1, 8, signed=False)
    RTL_SIM_TIME_MULTIPLIER = FP_TY.bit_length() + FP_TY.frac_bit_length + 1
    MODULE_CLS = FixpDivRemHwModule
    INPUT_DATA = [
       (1.0, 1.0),
       (1.0, 1.25),
       (1.25, 1.0),
       (0.5, 0.5),
       (0.25, 0.5),
    ]

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6),
                 platformKwArgs=dict(
                    # debugFilter={*HlsDebugBundle.ALL_RELIABLE,
                    #             # HlsDebugBundle.DBG_4_0_hwscheduleTrace,
                    #             # HlsDebugBundle.DBG_4_0_hwscheduleDumpAfterPhases,
                    #             # HlsDebugBundle.DBG_4_0_hwschedulePrintPhaseBoundaries,
                    #             # HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                    #             # HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                    #           },
                    llvmCliArgs=[
                        LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                       # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                       # LLVM_CLI_COMMON_OPTS.VREGIFCVT_TRACE,
                       # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                    ],)):
        dut = self.MODULE_CLS()
        dut.T = self.FP_TY
        dut.CLK_FREQ = freq
        dut.UNROLL_FACTOR = dut._getMaxIterationCount()

        FixpAlu2_TC.test_rtl(
            self, dut=dut, runTestAfterEachPass=runTestAfterEachPass,
            OUT_DATA_REF=(PassTestIoOutStructHFixedPoint2(dut.T, self.INPUT_DATA, [], maxErrorInt=mask(self.MAX_ULP), name="data_out"),),
            platformKwArgs=platformKwArgs,
        )


FixpOpCommonArith_TCs = [
    FixpAdd_TC,
    FixpSub_TC,
    FixpMul_TC,
    FixpDiv_TC,
    FixpDivUnroll_TC,
    FixpDiv_q1_8_TC,
]

if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    # from tests.math.installMathLib import installMathLibComponentGenerators
    # m = TestModuleFixpAdd()
    # m.T = HFixedPointQ(4, 8)
    # m.CLK_FREQ = int(1e6)
    # # platform = Artix7Fast(
    # platform = VirtualHlsPlatform(
    #     debugFilter=HlsDebugBundle.ALL_RELIABLE,
    #    # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL, ]
    # )
    # installMathLibComponentGenerators(platform)
    # print(to_rtl_str(m, target_platform=platform))

    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpCommonArith_TCs])
    # suite = unittest.TestSuite([FixpDiv_TC('test_rtl')])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

