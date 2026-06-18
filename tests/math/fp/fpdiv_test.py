#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import nan, inf

from hwt.pyUtils.typingFuture import override
from tests.math.componentGenerators._genericHwModules import _FpAlu2HwModule
from tests.math.componentGenerators.fdivrem import FpDivHwModule
from tests.math.fp._fpAlu2_TC import IEEE754FpAlu2_TC
from tests.math.fp.fpdiv import IEEE754FpDiv
from tests.math.fp.fptypes import IEEE754Fp64


class _FpGenAluDivHwModule(_FpAlu2HwModule):
    
    @override
    def FN(self, a, b, loopPragmaGetter=None):
        return a / b
    
    model = staticmethod(FpDivHwModule.model)


class IEEE754FpDiv_TC(IEEE754FpAlu2_TC):
    FP_FUNCTION = staticmethod(IEEE754FpDiv)
    FP_FUNCTION_HAS_SIM_ARG = False
    SIM_TIME_MULTIPLIER_IR_MIR = 3000
    FP_TY = IEEE754Fp64
    INPUT_DATA = [
        (1.0, 1.0),
        (1.0, -1.0),
        (4.0, 1.0),
        (4.0, 2.0),
        (4.0, 4.0),
        (4.0, 8.0),
        (1.125, 1.0),
        (1.0, 1.125),  # 0.888...
        (1.25, 1.0),
        (1.0, 2.0),
        (1.0, 2.25),  # 0.444...
        (nan, 1.0),
        (1.0, nan),
        (inf, 1.0),
        (1.0, inf),
        (-inf, 1.0),
        (inf, nan),
        # (sys.float_info.max, 1.0), # [todo] rounding in HFloatTmp conversion around fixpDiv
    ]
    optThroughputVsArea = 1.0
    MAX_TABLE_ADDR_WIDTH = 0
    model = staticmethod(FpDivHwModule.model)

    def test_ir_mir_rtl(self, freq=int(1e3)):
        # test that IEEE754FpAdd function works correctly
        dut = FpDivHwModule()
        dut.CLK_FREQ = freq
        dut.T = self.FP_TY
        self._test_ir_mir_rtl(dut, wallTimeRtlDefaultMultiplier=1.1)

    def test_gen_ir_mir_rtl(self, freq=int(1e3)):
        # test that component generator instantiates fadd correctly
        dut = _FpGenAluDivHwModule()
        dut.T = self.FP_TY
        dut.CLK_FREQ = freq
        self._test_ir_mir_rtl(dut, wallTimeRtlDefaultMultiplier=1.1)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from tests.math.installMathLib import installMathLibComponentGenerators
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast

    # m = _FpAlu2HwModule()
    # m.FN = IEEE754FpDiv
    # m.CLK_FREQ = int(100e3)
    # m.T = IEEE754Fp64
    # p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    # installMathLibComponentGenerators(p)
    # print(to_rtl_str(m, target_platform=p))

    import unittest

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(IEEE754FpDiv_TC)
    # suite = unittest.TestSuite([IEEE754FpDiv_TC('test_ir_mir_rtl')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
