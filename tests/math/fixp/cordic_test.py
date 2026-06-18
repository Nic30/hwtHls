#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
from typing import Sequence

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation, \
    HFloatTmpConfig, APInt
from hwtHls.platform.debugBundle import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from pyMathBitPrecise.bit_utils import mask, to_signed
from pyMathBitPrecise.bits3t import Bits3val
from tests.math.componentGenerators.fsincos import FixpSinCosCordic, \
    FixpSinCosCordicPi
from tests.math.fixp.cordicHybridLut import Cordic
from tests.math.fixp.fixpConst import HFixedPointQConst
from tests.math.fixp.fixpOperatorsTrigonometric_test import FixpSinNoLut_TC
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.installMathLib import installMathLibComponentGenerators
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.math.fixp.passTestIoFixp import PassTestIoInHFixedPoint,\
    PassTestIoOutStructHFixedPoint2


class Cordic_TC(SimTestCase):
    # DEFAULT_BUILD_DIR = "tmp/sim/"

    def _showSinCosErrorGraph(self, fpT: HFixedPointQ,
                                inputs: float,
                                sinCosPairs: Sequence[tuple[HBitsConst, HBitsConst]],
                                isSinCosPi:bool):
        bitVecT = HBits(fpT.bit_length(), signed=True)

        import matplotlib.pyplot as plt

        xInt = []
        xFloat = []

        sinYint = []
        sinYfloat = []
        sinYErrInt = []
        sinYErrFloat = []

        cosYint = []
        cosYfloat = []
        cosYErrInt = []
        cosYErrFloat = []

        def floatToBits(v: float):
            return fpT.from_py(v)._reinterpret_cast(bitVecT)

        if isinstance(sinCosPairs[0][0], HFixedPointQConst):

            def toInt(v: HFixedPointQConst):
                return int(v._reinterpret_cast(bitVecT))

            def toFloat(v: HFixedPointQConst):
                return v.to_py()

        else:
            toInt = int

            def bitsToFloat(v: Bits3val):
                return bitVecT._from_py(v.val, v.vld_mask)._reinterpret_cast(fpT).to_py()

            toFloat = bitsToFloat

        w = fpT.bit_length()
        for v, (sin, cos) in zip(inputs, sinCosPairs):
            sin: HFixedPointQConst
            cos: HFixedPointQConst
            xFloat.append(v)
            xInt.append(int(floatToBits(v)))

            if isSinCosPi:
                refSinF, refCosF = math.sin(v * math.pi), math.cos(v * math.pi)
            else:
                refSinF, refCosF = math.sin(v), math.cos(v)

            refSinInt, refCosInt = floatToBits(refSinF), floatToBits(refCosF)
            sinF, cosF = toFloat(sin), toFloat(cos)
            sinInt, cosInt = toInt(sin), toInt(cos)
            sinInt = to_signed(sinInt, w)
            cosInt = to_signed(cosInt, w)

            sinYint.append(sinInt)
            cosYint.append(cosInt)
            sinYfloat.append(sinF)
            cosYfloat.append(cosF)

            sinYErrInt.append(abs(sinInt - int(refSinInt)))
            cosYErrInt.append(abs(cosInt - int(refCosInt)))
            sinYErrFloat.append(abs(sinF - refSinF))
            cosYErrFloat.append(abs(cosF - refCosF))

        maxError = 2.0 ** -fpT.frac_bit_length  # 1 ULP
        fig, axs = plt.subplots(4, 2, figsize=(15, 15))
        axs[0, 0].set_ylabel("sin int")
        axs[0, 0].plot(xInt, sinYint)
        axs[1, 0].set_ylabel("sin err int")
        axs[1, 0].plot(xInt, sinYErrInt)
        axs[2, 0].set_ylabel("sin float")
        axs[2, 0].plot(xFloat, sinYfloat)
        axs[3, 0].set_ylabel("sin err float")
        axs[3, 0].plot(xFloat, sinYErrFloat)
        axs[3, 0].plot(xFloat, [maxError for _ in range(len(xFloat))], color="green")

        axs[0, 1].set_ylabel("cos int")
        axs[0, 1].plot(xInt, cosYint)
        axs[1, 1].set_ylabel("cos err int")
        axs[1, 1].plot(xInt, cosYErrInt)
        axs[2, 1].set_ylabel("cos float")
        axs[2, 1].plot(xFloat, cosYfloat)
        axs[3, 1].set_ylabel("cos err float")
        axs[3, 1].plot(xFloat, cosYErrFloat)
        axs[3, 1].plot(xFloat, [maxError for _ in range(len(xFloat))], color="green")
        for y in range(3):
            for x in range(2):
                axs[y, x].grid()
        plt.show()

    def _getAllValueForHFixedPointQ(self, fpT:HFixedPointQ):
        TEST_VALUES: list[float] = []
        cfg: HFloatTmpConfig = fpT._cfg
        # min (negative) -> 0
        w = fpT.bit_length()
        for i in range(1 << (w - 1), 1 << w):
            f = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(w, i))
            TEST_VALUES.append(float(f))
        # 0 -> max
        for i in range(0, 1 << (w - 1)):
            f = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(w, i))
            TEST_VALUES.append(float(f))
        return TEST_VALUES

    def test_py(self):
        # T = HFixedPointQ(10, 10)
        ITERATION_COUNT = 24 + 2
        STAGES_IN_LUT = 7

        hybridCordic = Cordic(ITERATION_COUNT, STAGES_IN_LUT=STAGES_IN_LUT)
        # angles = (# 0, 15, 30,
        #                       # 45,
        #                       # 60,
        #                       # 90,
        #                       180 , 270,
        #                       360
        #                       , 4000
        #                         )
        # angles = tuple(range(360 + 3))
        angles = tuple(range(0, 360 + 16, 15))
        # angles  = [30, ]
        maxErr = 0.0001

        # cos3_val, sin3_val = hybridCordic.cosSinPi(1.0 / math.pi)
        # print(cos3_val, math.cos(1.0))
        # return
        for angleDegre in angles:
            angleRad = math.radians(angleDegre)

            # cos1_val, sin1_val = cordic(angleRad, iterationCount=ITERATION_COUNT, dbgInPy=True)
            # cos1_val = float(cos1_val)
            # sin1_val = float(sin1_val)
            sin = math.sin(angleRad)
            cos = math.cos(angleRad)

            # cos2_val, sin2_val = hybridCordic.cosSin(angleRad)
            # cos2_val, sin2_val = float(cos2_val), float(sin2_val)
            cos3_val, sin3_val = hybridCordic.cosSinPi(angleRad / math.pi, isSim=True)
            cos3_val, sin3_val = float(cos3_val), float(sin3_val)
            # sin4_val = sin_custom(angleRad)

            # cos4_val, sin4_val = hybrid_cordic_no_division_pi(angleRad / math.pi, ITERATION_COUNT, STAGES_IN_LUT)
            # print(f"\nsin for {angleDegre}°, {angleRad:.8f} rad, {angleRad/math.pi:.8f} pi*rad:")  #
            # print(f"python                         : cos = {cos:.8f}, sin = {sin:.8f}")
            # print(f"hybrid_cordic_no_division      : cos ≈ {cos2_val:.8f}, sin ≈ {sin2_val:.8f}    diff: {cos2_val-cos:.8f}, {sin2_val-sin:.8f}")
            # print(f"hybrid_cordic_no_division_pi   : cos ≈ {cos3_val:.8f}, sin ≈ {sin3_val:.8f}    diff: {cos3_val-cos:.8f}, {sin3_val-sin:.8f}")
            # print(f"hybrid_cordic_no_division_pi2  : cos ≈ {cos4_val:.8f}, sin ≈ {sin4_val:.8f}    diff: {cos4_val-cos:.8f}, {sin4_val-sin:.8f}")
            # print(f"sin_custom                     : sin ≈ {sin4_val:.8f}    diff: {sin4_val-sin:.8f}")
            angleMsg = (angleDegre, angleRad, angleRad / math.pi)
            self.assertAlmostEqual(sin3_val, sin, msg=angleMsg, delta=maxErr)
            self.assertAlmostEqual(cos3_val, cos, msg=angleMsg, delta=maxErr)

    def test_SinCos_Q4_10_py(self,
                             fpT=HFixedPointQ(4, 10,
                                 rounding=HFloatTmpRounding.ROUND_FLOOR,
                                 saturation=HFloatTmpSaturation.SATURATE_NONE,
                                 signed=True),
                             TEST_VALUES=FixpSinNoLut_TC.INPUT_DATA,
                             STAGES_IN_LUT:int=0,
                             useSinCosPi=False,
                             ULP=2,
                             ):
        bitVecT = HBits(fpT.bit_length(), signed=True)
        ITERATION_COUNT = FixpSinCosCordic._getMaxIterationCountForTy(fpT)

        def floatToBits(v: float):
            return fpT.from_py(v)._reinterpret_cast(bitVecT)

        def bitsToFloat(v: Bits3val):
            return  float(bitVecT._from_py(v.val, v.vld_mask)._reinterpret_cast(fpT))

        def castHFloatTmpToPyFloat(v):
            return float(v)

        cordic = Cordic(ITERATION_COUNT,
                        STAGES_IN_LUT=STAGES_IN_LUT,
                        # dbgLogFile=sys.stdout,
                        )
        if ULP == 0.5:
            maxError = 2.0 ** -(fpT.frac_bit_length + 1)  # 1 ULP # because alg. runs using python float (double) and is rounded at end
        else:
            assert isinstance(ULP, int), ULP
            assert fpT.frac_bit_length > ULP, (fpT.frac_bit_length, ULP)
            maxError = 2.0 ** -(fpT.frac_bit_length - ULP)
        # fpT_p2b = fpT._createMutated(frac_bit_length=fpT.frac_bit_length + 2)
        # resuls = []
        for v in TEST_VALUES:
            inp = fpT.from_py(v)
            self.assertEqual(float(inp), v, "No rounding during input cast")
            if useSinCosPi:
                refSinVal = math.sin(v * math.pi)
                refCosVal = math.cos(v * math.pi)
                resCos, resSin = cordic.cosSinPi(inp, isSim=True)
            else:
                refSinVal = math.sin(v)
                refCosVal = math.cos(v)
                resCos, resSin = cordic.cosSin(inp, isSim=True)

            self.assertAlmostEqual(castHFloatTmpToPyFloat(resSin), refSinVal,
                                  msg=(v, resSin, fpT.from_py(refSinVal), maxError),
                                  delta=maxError)
            self.assertAlmostEqual(castHFloatTmpToPyFloat(resCos), refCosVal,
                                  msg=(v, resCos, fpT.from_py(refCosVal), maxError),
                                  delta=maxError)

            # resuls.append((resSin, resCos))
        # self._showSinCosErrorGraph(fpT, TEST_VALUES, resuls, useSinCosPi)

    def test_SinCos_Q4_10_rtl(self,
                              fpT=HFixedPointQ(4, 10,
                                 rounding=HFloatTmpRounding.ROUND_FLOOR,
                                 saturation=HFloatTmpSaturation.SATURATE_NONE,
                                 signed=True),
                             TEST_VALUES=FixpSinNoLut_TC.INPUT_DATA,
                             STAGES_IN_LUT:int=0,
                             RTL_SIM_TIME_MULTIPLIER=1.0,
                             UNROLL_FACTOR=None,
                             useSinCosPi=False,
                             ULP=2,
                              ):
        if useSinCosPi:
            dut = FixpSinCosCordicPi()
        else:
            dut = FixpSinCosCordic()
        # dut.dbgLogFile = sys.stdout
        dut.T = fpT
        dut.STAGES_IN_LUT = STAGES_IN_LUT
        dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        dut.ITERATION_COUNT = FixpSinCosCordic._getMaxIterationCountForTy(fpT)
        if UNROLL_FACTOR is None:
            UNROLL_FACTOR = dut.ITERATION_COUNT - STAGES_IN_LUT
        dut.UNROLL_FACTOR = UNROLL_FACTOR
        # bitVecT = HBits(fpT.bit_length())

        # def bitsToFloat(v: Bits3val):
        #    return bitVecT._from_py(v.val, v.vld_mask)._reinterpret_cast(fpT).to_py()

        ref: list[tuple[float, float]] = []  # :note: tuples (cos(x), sin(x))
        for v in TEST_VALUES:
            if useSinCosPi:
                refCosVal = math.cos(v * math.pi)
                refSinVal = math.sin(v * math.pi)
            else:
                refCosVal = math.cos(v)
                refSinVal = math.sin(v)
            ref.append((refSinVal, refCosVal))

        if ULP <= 0:
            maxErrorInt = 0
        else:
            maxErrorInt = mask(ULP)

        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.bindData((PassTestIoInHFixedPoint(fpT, TEST_VALUES),
                            PassTestIoOutStructHFixedPoint2(fpT, TEST_VALUES, ref, name="data_out", maxErrorInt=maxErrorInt),))
        platform = VirtualHlsPlatform(
            # debugFilter={*HlsDebugBundle.ALL_RELIABLE},
            # llvmCliArgs=[
            #     # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED
            # ]
        )
        installMathLibComponentGenerators(platform)
        passTests.setTimeLimits(wallTimeRtl=(len(ref) * dut.ITERATION_COUNT + 2) * RTL_SIM_TIME_MULTIPLIER)
        passTests.test_allInOne(platform=platform)

    def test_SinCos_Q4_10_rtl_noUnroll(self):
        self.test_SinCos_Q4_10_rtl(UNROLL_FACTOR=0, RTL_SIM_TIME_MULTIPLIER=4)

    def test_SinCos_Q4_4_py_all(self,
                             fpT=HFixedPointQ(4, 4,
                                 rounding=HFloatTmpRounding.ROUND_FLOOR,
                                 saturation=HFloatTmpSaturation.SATURATE_NONE,
                                 signed=True),
                              STAGES_IN_LUT=0,
                              ULP=3,
                              useSinCosPi=False,
                             ):
        TEST_VALUES = self._getAllValueForHFixedPointQ(fpT)
        self.test_SinCos_Q4_10_py(fpT, TEST_VALUES, STAGES_IN_LUT=STAGES_IN_LUT, ULP=ULP, useSinCosPi=useSinCosPi)

    def test_SinCosPi_Q4_4_py_all(self):
        self.test_SinCos_Q4_4_py_all(useSinCosPi=True, ULP=1)

    def test_SinCos_Q4_4_py_lut2_all(self):
        self.test_SinCos_Q4_4_py_all(STAGES_IN_LUT=2, ULP=3)

    def test_SinCosPi_Q4_4_lut2_py_all(self):
        self.test_SinCos_Q4_4_py_all(STAGES_IN_LUT=2, ULP=1, useSinCosPi=True)

    def test_SinCos_Q4_4_rtl_all(self,
                             fpT=HFixedPointQ(4, 4,
                                 rounding=HFloatTmpRounding.ROUND_FLOOR,
                                 saturation=HFloatTmpSaturation.SATURATE_NONE,
                                 signed=True),
                              STAGES_IN_LUT=0,
                              ULP=3,
                              useSinCosPi=False,
                             ):
        TEST_VALUES = self._getAllValueForHFixedPointQ(fpT)
        self.test_SinCos_Q4_10_rtl(fpT, TEST_VALUES, STAGES_IN_LUT=STAGES_IN_LUT, ULP=ULP, useSinCosPi=useSinCosPi)

    def test_SinCosPi_Q4_4_rtl_all(self):
        self.test_SinCos_Q4_4_rtl_all(useSinCosPi=True, ULP=1)

    def test_SinCos_Q4_4_rtl_lut2_all(self):
        self.test_SinCos_Q4_4_rtl_all(STAGES_IN_LUT=2, ULP=3)

    def test_SinCosPi_Q4_4_lut2_rtl_all(self):
        self.test_SinCos_Q4_4_rtl_all(STAGES_IN_LUT=2, ULP=1, useSinCosPi=True)


if __name__ == '__main__':
    import sys
    import unittest
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from hwt.synth import to_rtl_str
    m = FixpSinCosCordic()
    # m.dbgLogFile = sys.stdout
    fpT = m.T = HFixedPointQ(4, 10,
             rounding=HFloatTmpRounding.ROUND_FLOOR,
             saturation=HFloatTmpSaturation.SATURATE_NONE,
             signed=True)
    m.IN_CHANNEL_TYPE = HwIOStructRdVld
    m.ITERATION_COUNT = FixpSinCosCordic._getMaxIterationCountForTy(fpT)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
                              # LLVM_CLI_COMMON_OPTS.filterPrintFuncs(["FixpSinCosCordic.mainThread",]),
                              # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                              # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_ARGUMENTS,
                              # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                              # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                          ]
                          )
    installMathLibComponentGenerators(platform)
    # print(to_rtl_str(m, target_platform=platform))

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Cordic_TC)
    # suite = unittest.TestSuite([Cordic_TC('test_SinCos_Q4_10_rtl')])
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())

