#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInline
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from tests.math.fixp.cordicAngleNormalization import anglePiRadsTo0_to_2, \
    getOctantPiRads, normalizeOctantPiradsTo0_to_0_25, \
    cordic_withNormalization0_to_0_25
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.fixp.fixpOperatorsTrigonometric_test import FixpSinNoLutUnroll_TC
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpAdd_TC


class _CordicAngleNormalizationTestModule(_BaseALU1HwModule):

    def hwConfig(self) -> None:
        _BaseALU1HwModule.hwConfig(self)
        self.IN_CHANNEL_TYPE = HwIOStructRdVld

    def hwDeclr(self) -> None:
        addClkRstn(self)
        t = self.T
        assert t is not None, self
        self._addDataInDataOut(
            HBits(t.bit_length()),
            HStruct(
                (HBits(HFixedPointQ(2, t.frac_bit_length, signed=False).bit_length()), "value"),
                (BIT, "swapXY"),
                (BIT, "negateX"),
                (BIT, "negateY"),
            )
        )

    @hlsBytecode
    def aluFn(self, _inp):
        T = self.T
        anglePiRad = _inp._reinterpret_cast(T)._auto_cast(HFloatTmp)
        _anglePiRadTmp = PyBytecodeInline(anglePiRadsTo0_to_2)(anglePiRad)
        if isinstance(T, HFixedPointQ) and (T.int_bit_length > 2 or T.signed):
            # needs range reduction
            _anglePiRad0to2 = _anglePiRadTmp._auto_cast(T)._auto_cast(T._createMutated(int_bit_length=2, signed=False))
            T = _anglePiRad0to2._dtype
        else:
            _anglePiRad0to2 = _anglePiRadTmp

        octant = getOctantPiRads(_anglePiRad0to2)
        octantNormTy = _anglePiRad0to2._dtype._createMutated(int_bit_length=3, signed=True)
        anglePiRad0to2 = _anglePiRad0to2._auto_cast(octantNormTy)._auto_cast(HFloatTmp)

        swapXY, negateX, negateY, _anglePiRad0to0_25Tmp = PyBytecodeInline(normalizeOctantPiradsTo0_to_0_25)(
            octant, anglePiRad0to2)
        _anglePiRad0to0_25 = _anglePiRad0to0_25Tmp._auto_cast(octantNormTy)
        
        resTmp = self._getTypeOfIo(self.data_out).from_py(None)
        resTmp.value = _anglePiRad0to0_25._auto_cast(T)._reinterpret_cast(resTmp.value._dtype)
        resTmp.swapXY = swapXY
        resTmp.negateX = negateX
        resTmp.negateY = negateY
        return resTmp


class CordicAngleNormalization_TC(FixpSinNoLutUnroll_TC):
    FP_TY = HFixedPointQ(4, 8, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    RTL_SIM_TIME_MULTIPLIER = 1.0
    INPUT_DATA = [
         #0.5,
         *(0.0625 * i for i in range(int((2 / 0.0625) * 1.2))),
         *(-0.0625 * i for i in range(int((2 / 0.0625) * 1.2))),
         # 0.0,
         # 0.1, 0.2, 0.25, 0.5,
         # 1.0
    ] 

    def _model(self, a: float) -> float:
        return cordic_withNormalization0_to_0_25(a)

    def prepareDataInFn(self):
        fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())
        dataIn = []
        for a in self.INPUT_DATA:
            a = fpTy.from_py(a)._reinterpret_cast(bitTy)
            dataIn.append(a)
        return dataIn

    def prepareDataInFnRtl(self):
        fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())
        for a in self.INPUT_DATA:
            a = fpTy.from_py(a)._reinterpret_cast(bitTy)
            yield a

    def getCheckDataOutFn(self, REF_DATA):
        fpTy: HFixedPointQ = self.FP_TY
        bitTy = HBits(fpTy.bit_length())
        outFpTy = fpTy._createMutated(int_bit_length=2)
        outBitTy = HBits(outFpTy.bit_length())

        def toFloat(v):
            assert v._dtype.bit_length() == outBitTy.bit_length(), (v, outBitTy)
            return float(outBitTy.from_py(v.val, v.vld_mask)._reinterpret_cast(outFpTy)) if v._is_full_valid() else v

        def toBool(v):
            return bool(v) if v._is_full_valid() else None

        def checkDataOutFn(dataOut):
            dataOutRef = []
            for v, swapXY, negateX, negateY in REF_DATA:
                ref = (int(fpTy.from_py(v)._reinterpret_cast(bitTy)),
                       int(swapXY), int(negateX), int(negateY))
                dataOutRef.append(ref)
            _dataOut = [(toFloat(v[0]), toBool(v[1]), toBool(v[2]), toBool(v[3])) for v in dataOut]
            self.assertSequenceEqual(_dataOut, REF_DATA, (self.INPUT_DATA, dataOut, "!=", dataOutRef)
            )

        return  checkDataOutFn

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = _CordicAngleNormalizationTestModule()
        dut.T = self.FP_TY
        dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        dut.CLK_FREQ = freq
        FixpAdd_TC.test_rtl(self, runTestAfterEachPass, freq, dut=dut)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    # from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast
    # from tests.math.componentGenerators.install import installFpComponentGenerators

    # m = _CordicAngleNormalizationTestModule()
    # m.CLK_FREQ = int(1e6)
    # m.T = HFixedPointQ(4, 8, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    # platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
    #                      llvmCliArgs=[
    #                          # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
    #                          LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
    #                      ]
    #                      )
    # installFpComponentGenerators(platform)
    # print(to_rtl_str(m, target_platform=platform))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpDiv_TC('test_div_py')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in [CordicAngleNormalization_TC, ]])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
