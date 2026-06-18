#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.math.componentGenerators._genericHwModules import _FpAlu2HwModule
from tests.math.componentGenerators.fmul import FpMulHwModule
from tests.math.fp._fpAlu2_TC import IEEE754FpAlu2_TC
from tests.math.fp.fpadd_test import IEEE754FpAdd_TC
from tests.math.fp.fpmul import IEEE754FpMul
from tests.math.fp.fptypes import IEEE754Fp64


class _FpGenAluMulHwModule(_FpAlu2HwModule):

    FN = model = staticmethod(FpMulHwModule.model)


class IEEE754FpMultipier_TC(IEEE754FpAlu2_TC):
    FP_FUNCTION = staticmethod(IEEE754FpMul)
    model = model = staticmethod(FpMulHwModule.model)
    FP_FUNCTION_HAS_SIM_ARG = False
    SIM_TIME_MULTIPLIER_IR_MIR = 250
    INPUT_DATA = IEEE754FpAdd_TC.INPUT_DATA
    FP_TY = IEEE754Fp64

    def test_ir_mir_rtl(self, freq=int(1e3)):
        # test that IEEE754FpAdd function works correctly
        dut = FpMulHwModule()
        dut.CLK_FREQ = freq
        dut.T = self.FP_TY
        self._test_ir_mir_rtl(dut)

    def test_gen_ir_mir_rtl(self, freq=int(1e3)):
        # test that component generator instantiates fadd correctly
        dut = _FpGenAluMulHwModule()
        dut.T = self.FP_TY
        dut.CLK_FREQ = freq
        self._test_ir_mir_rtl(dut)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from tests.math.fp.fptypes import IEEE754Fp16
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast

    m = _FpAlu2HwModule()
    m.FN = IEEE754FpMul
    m.CLK_FREQ = int(100e3)
    m.T = IEEE754Fp16

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpMultipier_TC('test_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpMultipier_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
