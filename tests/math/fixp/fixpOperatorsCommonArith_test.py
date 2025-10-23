#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.serializer.mode import serializeParamsUniq
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
from tests.math.installMathLib import installMathLibComponentGenerators
from tests.math.fixp.fixpOperatorsHwModules import _FixpBinOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixpdivrem import fixpDivremRestoring
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform
from tests.math.fixp._fixpUnary_TC import FixpUnary_TC


@serializeParamsUniq
class TestModuleFixpAdd(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a + b


class FixpAdd_TC(SimTestCase):
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

    def _model(self, a: float, b: float) -> float:
        return a + b

    def _getRefData(self, input_data):
        return [self._model(*d) for d in input_data]

    def prepareDataInFn(self):
        fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())
        dataIn = []
        for (a, b) in self.INPUT_DATA:
            a = fpTy.from_py(a)._reinterpret_cast(bitTy)
            b = fpTy.from_py(b)._reinterpret_cast(bitTy)
            dataIn.append(Concat(b, a))
        return dataIn

    def prepareDataInFnRtl(self):
        fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())
        for (a, b) in self.INPUT_DATA:
            a = fpTy.from_py(a)._reinterpret_cast(bitTy)
            b = fpTy.from_py(b)._reinterpret_cast(bitTy)
            yield (a, b)

    def getCheckDataOutFn(self, REF_DATA):
        return FixpUnary_TC.getCheckDataOutFn(self, REF_DATA)

    def initPlatform(self, target_platform:TestLlvmIrAndMirPlatform):
        FixpUnary_TC.initPlatform(self, target_platform)

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6), dut=None):
        if dut is None:
            dut = self.MODULE_CLS()
            dut.T = self.FP_TY
            dut.CLK_FREQ = freq

        FixpUnary_TC._test_rtl(self, dut, runTestAfterEachPass)


@serializeParamsUniq
class TestModuleFixpSub(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a - b


class FixpSub_TC(FixpAdd_TC):

    MODULE_CLS = TestModuleFixpSub

    def _model(self, a: float, b: float) -> float:
        return a - b


@serializeParamsUniq
class TestModuleFixpMul(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a * b


class FixpMul_TC(FixpAdd_TC):
    MODULE_CLS = TestModuleFixpMul

    def _model(self, a: float, b: float) -> float:
        return a * b


@serializeParamsUniq
class TestModuleFixpDiv(_FixpBinOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a / b


class FixpDiv_TC(FixpAdd_TC):
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

    MODULE_CLS = TestModuleFixpDiv

    def _model(self, a: float, b: float) -> float:
        return a / b

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
                (dividend, "//", divisor, "==", (quotient, remainder), (int(toBitVecFloat(quotient)), int(toBitVecFloat(remainder)))),
                ("res:", (toFloat(_quotient), toFloat(_remainder)), (_quotient, _remainder))
            )
            self.assertAlmostEqual(toFloat(_quotient), quotient, msg=msg, delta=0.001)
            self.assertAlmostEqual(toFloat(_remainder), remainder, msg=msg, delta=0.001)


class FixpDivUnroll_TC(FixpDiv_TC):
    optThroughputVsArea = 1.0


FixpOpCommonArith_TCs = [
    FixpAdd_TC,
    FixpSub_TC,
    FixpMul_TC,
    FixpDiv_TC,
    FixpDivUnroll_TC,
]

if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from hwtHls.platform.virtual import VirtualHlsPlatform
    m = TestModuleFixpAdd()
    m.T = HFixedPointQ(4, 8)
    m.CLK_FREQ = int(1e6)
    # platform = Artix7Fast(
    platform = VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
       # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL, ]
    )
    installMathLibComponentGenerators(platform)
    print(to_rtl_str(m, target_platform=platform))

    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpCommonArith_TCs])
    # suite = unittest.TestSuite([FixpDiv_TC('test_rtl')])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

