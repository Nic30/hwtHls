#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import nan, inf
import sys

from hwt.pyUtils.typingFuture import override
from hwtHls.platform.virtual import VirtualHlsPlatform
from tests.math.componentGenerators._genericHwModules import _FpAlu2HwModule
from tests.math.componentGenerators.fadd import FpAddHwModule
from tests.math.fp._fpAlu2_TC import IEEE754FpAlu2_TC
from tests.math.fp.fpadd import IEEE754FpAdd
from tests.math.fp.fptypes import IEEE754Fp64
from tests.math.installMathLib import installMathLibComponentGenerators
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


assert sys.float_info.mant_dig == 53


class _FpGenAluAddHwModule(_FpAlu2HwModule):
    
    @override
    def FN(self, a, b, loopPragmaGetter=None):
        return a + b
    
    model = staticmethod(FpAddHwModule.model)

    
class IEEE754FpAdd_TC(IEEE754FpAlu2_TC):
    """
    :cvar FP_FUNCTION: the function which implements the operation using lower level operations
    :cvar FP_OPERATOR_FN: the function which performs the operation using operator function
        which is then mapped to component with FP_FUNCTION by the backend
    """
    INPUT_DATA = [
        (1.0, 1.0),
        (1.0, -1.0),
        (1.125, 1.0),
        (1.25, 1.0),
        (1.0, 2.0),
        (1.0, 2.25),
        (nan, 1.0),
        (inf, 1.0),
        (-inf, 1.0),
        (inf, nan),
        (sys.float_info.max, 1.0),
        (sys.float_info.epsilon, sys.float_info.epsilon),
    ]

    SIM_TIME_MULTIPLIER_IR_MIR = 300
    FP_TY = IEEE754Fp64
    optThroughputVsArea = 0.0
    MAX_TABLE_ADDR_WIDTH = 7

    # :note: staticmethod must be used otherwise function is bounded as instance method to this class
    #  and it add "self" parameter
    FP_FUNCTION = staticmethod(IEEE754FpAdd)
    FP_FUNCTION_HAS_SIM_ARG = True
    model = staticmethod(FpAddHwModule.model)

    def test_ir_mir_rtl(self, freq=int(1e3)):
        # test that IEEE754FpAdd function works correctly
        dut = FpAddHwModule()
        dut.CLK_FREQ = freq
        dut.T = self.FP_TY
        self._test_ir_mir_rtl(dut)

    def test_gen_ir_mir_rtl(self, freq=int(1e3)):
        # test that component generator instantiates fadd correctly
        dut = _FpGenAluAddHwModule()
        dut.T = self.FP_TY
        dut.CLK_FREQ = freq
        self._test_ir_mir_rtl(dut)


class _FpGenAluSubHwModule(_FpAlu2HwModule):
    
    @override
    def FN(self, a, b, loopPragmaGetter=None):
        return a - b
    
    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True, inputArgsAreStructMembers=True)
    def model(a: float, b: float) -> float:
        return a - b


class IEEE754FpSub_TC(IEEE754FpAdd_TC):
    model = staticmethod(_FpGenAluSubHwModule.model)

    # :note: this should also test OP_FNEG
    def test_py(self):
        pass  # dissable this test because there is no  FP_FUNCTION like IEEE754FpSub and operation is lowered to IEEE754FpAdd

    def test_ir_mir_rtl(self):
        pass  # :see: IEEE754FpSub_TC.test_py

    def test_gen_ir_mir_rtl(self, freq=int(1e3)):
        # test that component generator instantiates fsub correctly
        dut = _FpGenAluSubHwModule()
        dut.T = self.FP_TY
        dut.CLK_FREQ = freq
        self._test_ir_mir_rtl(dut)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast

    m = _FpAlu2HwModule()
    m.CLK_FREQ = int(100e3)
    m.T = IEEE754Fp64
    m.FN = lambda a, b: a - b
    p = VirtualHlsPlatform(# debugFilter=HlsDebugBundle.ALL_RELIABLE,
        llvmCliArgs=[
            # LLVM_CLI_COMMON_OPTS.TIME_PASSES,
            # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
        ]
    )
    installMathLibComponentGenerators(p)
    # print(to_rtl_str(m, target_platform=p))

    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in (IEEE754FpAdd_TC, IEEE754FpSub_TC)])
    # suite = testLoader.loadTestsFromTestCase(IEEE754FpAdd_TC)
    # suite = unittest.TestSuite([IEEE754FpAdd_TC('test_py')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
