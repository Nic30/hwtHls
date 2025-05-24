#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from hwt.simulator.simTestCase import SimTestCase
from tests.math.fixp.cordicHybridLut import Cordic


class Cordic_TC(SimTestCase):

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
            cos3_val, sin3_val = hybridCordic.cosSinPi(angleRad / math.pi)
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

    # def test_SinCos_Q2_8_py(self):
    #    fpT = self.FP_TY
    #    bitVecT = HBits(fpT.bit_length())
    #    ITERATION_COUNT = 2 + 6
    #
    #    def floatToBits(v: float):
    #        return fpT.from_py(v)._reinterpret_cast(bitVecT)
    #
    #    def bitsToFloat(v: Bits3val):
    #        return  float(bitVecT._from_py(v.val, v.vld_mask)._reinterpret_cast(fpT))
    #
    #    def castedHFloatTmpToPyFloat(v):
    #        assert v._rtlDrivers[0].operator == OP_CAST_FROM_HFLOATTMP, v
    #        return float(v._rtlDrivers[0].operands[0])
    #
    #    for v in self.TEST_VALUES:
    #        refSinVal = math.sin(v)
    #        refCosVal = math.cos(v)
    #        inp = fpT.from_py(v)
    #        resCos, resSin = cordic(inp, iterationCount=ITERATION_COUNT, dbgInPy=True)
    #        self.assertAlmostEqual(castedHFloatTmpToPyFloat(resSin), refSinVal, msg=v, delta=0.01)
    #        self.assertAlmostEqual(castedHFloatTmpToPyFloat(resCos), refCosVal, msg=v, delta=0.01)
    #
    # def test_SinCos_Q2_8(self):
    #    dut = FixpCosSinCordic()
    #    dut.IN_CHANNEL_TYPE = HwIOStructRdVld
    #    dut.ITERATION_COUNT = 2 + 6
    #    fpT = dut.T
    #    bitVecT = HBits(fpT.bit_length())
    #
    #    def floatToBits(v: float):
    #        return fpT.from_py(v)._reinterpret_cast(bitVecT)
    #
    #    def bitsToFloat(v: Bits3val):
    #        return float(bitVecT._from_py(v.val, v.vld_mask)._reinterpret_cast(fpT))
    #
    #    test_values = [floatToBits(v) for v in self.TEST_VALUES]
    #
    #    ref = []
    #    for v in self.TEST_VALUES:
    #        refCosVal = math.cos(v)
    #        refSinVal = math.sin(v)
    #        ref.append((floatToBits(refCosVal), floatToBits(refSinVal)))
    #
    #    def prepareDataInFn():
    #        return copy(test_values)
    #
    #    def checkDataOutFn(dataOut):
    #        assert dataOut
    #        w = fpT.bit_length()
    #        for i, (inpD, (refCos, refSin), d) in enumerate(zip_longest(test_values, ref, dataOut)):
    #            self.assertIsNotNone(ref, ("Output data contains more data then was expected", dataOut[len(ref):]))
    #            self.assertIsNotNone(d, ("Output data is missing data", ref[len(dataOut):]))
    #            cos = d[w:]
    #            sin = d[:w]
    #            self.assertValSequenceEqual((cos, sin), (refCos, refSin), (i, bitsToFloat(inpD),
    #                                                                       (bitsToFloat(cos), bitsToFloat(sin)),
    #                                                                       (bitsToFloat(refCos), bitsToFloat(refSin))))
    #
    #    #checkDataOutFn = None
    #    p = TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
    #        prepareDataInFn, checkDataOutFn, None,
    #        inputCnt=1,
    #        # noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
    #        #runTestAfterEachPass=True,
    #        llvmCliArgs=[
    #            #LLVM_CLI_COMMON_OPTS.PRINT_CHANGED
    #        ]
    #    )
    #    installFpComponentGenerators(p)
    #    self.compileSimAndStart(dut, target_platform=p)
    #
    #    dut.data_in._ag.data.extend(test_values)
    #
    #    self.runSim(int((len(ref) * dut.ITERATION_COUNT + 2) * freq_to_period(dut.CLK_FREQ)))
    #
    #    self.assertValSequenceEqual(dut.data_out._ag.data, ref,
    #                                msg=[(inp,
    #                                      (bitsToFloat(v[0]), bitsToFloat(v[1])),
    #                                      (bitsToFloat(vRef[0]), bitsToFloat(vRef[1])),
    #                                     )
    #                                 for inp, v, vRef in zip(self.TEST_VALUES, dut.data_out._ag.data, ref)
    #                                 ])
    #


if __name__ == '__main__':
    import sys
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Cordic_TC('test_SinCos_Q2_8_py')])
    suite = testLoader.loadTestsFromTestCase(Cordic_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
