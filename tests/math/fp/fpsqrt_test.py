#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import nan, inf

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.pyUtils.typingFuture import override
from hwtHls.code import ashr
from pyMathBitPrecise.bit_utils import to_unsigned
from tests.math.componentGenerators._genericHwModules import _FpAlu1HwModule
from tests.math.componentGenerators.fsqrt import FpSqrtHwModule
from tests.math.fp._fpAlu1_TC import IEEE754FpAlu1_TC
from tests.math.fp.fpsqrt import IEEE754FpSqrt, exponentBiasedDiv2
from tests.math.fp.fptypes import IEEE754Fp64, IEEE754Fp16
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import sqrt


class _FpGenSqrtHwModule(_FpAlu1HwModule):

    @override
    @staticmethod
    def FN(a: IEEE754Fp64):
        T = a._dtype
        return sqrt(a._explicit_cast(HFloatTmp))._explicit_cast(T)

    model = staticmethod(FpSqrtHwModule.model)


class IEEE754FpSqrt_TC(IEEE754FpAlu1_TC):
    FP_FUNCTION = staticmethod(IEEE754FpSqrt)
    FP_FUNCTION_HAS_SIM_ARG = False
    SIM_TIME_MULTIPLIER_IR_MIR = 3000
    FP_TY = IEEE754Fp16
    INPUT_DATA = [
        1.0,
        # (2.0, # [fixme] last digit rounded incorrectly
        4.0,
        9.0,
        # 0.5,
        0.25,
        # 0.75,
        1.5625,  # (1.25)**2
        0.0,
        nan,
        inf,
        -inf,
        # sys.float_info.max,
    ]

    model = staticmethod(FpSqrtHwModule.model)

    def test_biassedExponentDiv2(self):
        expTy = HBits(IEEE754Fp16.EXPONENT_WIDTH).from_py
        bias = IEEE754Fp16.EXPONENT_OFFSET
        biasU = IEEE754Fp16.EXPONENT_OFFSET_U
        W = IEEE754Fp16.EXPONENT_WIDTH
        for i in range(1 << W):
            # v = i + bias
            # ref = (i + bias) // 2 - bias
            # ref = (i + bias) // 2 - bias
            tmp0_0 = (i + bias)
            tmp0_1 = tmp0_0 // 2
            o0 = tmp0_1 - bias

            # signed division to shift # ._zext(W + 1)
            tmp1_0 = expTy(i)._zext(W + 1) + expTy(biasU)._sext(W + 1)
            # print("1", i, to_unsigned(tmp0_0, W), int(tmp1_0))

            tmp1_1 = ashr(tmp1_0, 1)._trunc(W)  # Concat(tmp1_0.getMsb(), tmp1_0[:1])._trunc(W)
            # print("2", i, to_unsigned(tmp0_1, W), int(tmp1_1))

            o1 = tmp1_1 - biasU
            # print("out", i, to_unsigned(o0, W), int(o1))

            self.assertEqual(o0, int(o1), (i,
                                           "tmp1_0:", to_unsigned(i + bias, W), int(tmp1_0),
                                           "tmp1_1:", (i + bias) // 2, int(tmp1_1)))

            # :note: _trunc moved at the end
            tmp2_0 = expTy(i)._zext(W + 1) + expTy(biasU)._sext(W + 1)
            # print("1", i, to_unsigned(tmp0_0, W), int(tmp1_0))

            tmp2_1 = ashr(tmp2_0, 1)
            # print("2", i, to_unsigned(tmp0_1, W), int(tmp1_1))

            o2 = (tmp2_1 - expTy(biasU)._sext(W + 1))._trunc(W)
            self.assertEqual(o0, int(o2), (i,
                                           "tmp1_0:", to_unsigned(i + bias, W), int(tmp2_0),
                                           "tmp1_1:", (i + bias) // 2, int(tmp2_1)))

            # :note: - bias sinked into ashr
            tmp3_0 = expTy(i)._zext(W + 1) + (expTy(biasU)._sext(W + 1) - (expTy(biasU)._sext(W + 1) << 1))
            tmp3_1 = ashr(tmp3_0, 1)
            o3 = tmp3_1._trunc(W)
            self.assertEqual(o0, int(o3), (i,
                                           "tmp1_0:", to_unsigned(i + bias, W), int(tmp3_0),
                                           "tmp1_1:", (i + bias) // 2, int(tmp3_1)))
            self.assertEqual(o0, int(exponentBiasedDiv2(IEEE754Fp16, expTy(i))), i)

            # res = halve_biased_number(i)
            # refB = v // 2
            # print(f"{i:05b}  {to_unsigned(refB - bias, 5):05b}")
            # self.assertEqual(res + bias, refB, ("v:", i, v, "resB:", res, "refB:", refB - bias))

    # @expectedFailure  # see test_py
    def test_ir_mir_rtl(self):
        dut = FpSqrtHwModule()
        dut.CLK_FREQ = int(1e3)
        dut.T = self.FP_TY
        dut.UNROLL_FACTOR = dut._getMaxIterationCount()
        dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        dut.OUT_CHANNEL_TYPE = HwIOStructRdVld
        self._test_ir_mir_rtl(dut)

    # @expectedFailure  # see test_py
    def test_gen_ir_mir_rtl(self):
        # test that component generator instantiates fadd correctly
        dut = _FpGenSqrtHwModule()
        dut.T = self.FP_TY
        dut.CLK_FREQ = int(1e3)
        dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        dut.OUT_CHANNEL_TYPE = HwIOStructRdVld
        self._test_ir_mir_rtl(dut,
            # platformKwArgs=dict(
            #     debugFilter={*HlsDebugBundle.ALL_RELIABLE}
            # )
        )


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast

    # m = _FpAlu1HwModule()
    # m.FN = IEEE754FpSqrt
    # m.CLK_FREQ = int(100e3)
    # m.T = IEEE754Fp16
    #
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(IEEE754FpSqrt_TC)
    # suite = unittest.TestSuite([IEEE754FpSqrt_TC('test_gen_ir_mir_rtl')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
