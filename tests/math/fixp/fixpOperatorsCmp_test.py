#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpAdd_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpCmpOpTestModule


class FixpCmp_OLT_TC(FixpAdd_TC):
    FP_TY = HFixedPointQ(3, 4)

    def HLS_OP_FN(self, a, b):
        return a < b

    def _model(self, a: float, b: float) -> bool:
        return int(self.HLS_OP_FN(a, b))  # int to have visually shorter output

    def getCheckDataOutFn(self, REF_DATA):

        def checkDataOutFn(dataOut):
            self.assertValSequenceEqual(dataOut, REF_DATA)

        return  checkDataOutFn

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = _FixpCmpOpTestModule()
        dut.T = self.FP_TY
        dut.CLK_FREQ = freq
        dut.FN = self.HLS_OP_FN
        FixpAdd_TC.test_rtl(self, runTestAfterEachPass, freq, dut=dut)


class FixpCmp_OLE_TC(FixpCmp_OLT_TC):

    def HLS_OP_FN(self, a, b):
        return a <= b


class FixpCmp_OEQ_TC(FixpCmp_OLT_TC):

    def HLS_OP_FN(self, a, b):
        return a._eq(b)

    def _model(self, a: float, b: float) -> bool:
        return int(a == b)  # int to have visually shorter output


class FixpCmp_ONE_TC(FixpCmp_OLT_TC):

    def HLS_OP_FN(self, a, b):
        return a != b


class FixpCmp_OGT_TC(FixpCmp_OLT_TC):

    def HLS_OP_FN(self, a, b):
        return a > b


class FixpCmp_OGE_TC(FixpCmp_OLT_TC):

    def HLS_OP_FN(self, a, b):
        return a >= b


FixpOpCmp_TCs = [
    FixpCmp_OLT_TC,
    FixpCmp_OLE_TC,
    FixpCmp_OEQ_TC,
    FixpCmp_ONE_TC,
    FixpCmp_OGT_TC,
    FixpCmp_OGE_TC
]

if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.installMathLib import installMathLibComponentGenerators

    m = _FixpCmpOpTestModule()
    m.FN = lambda a, b: a._eq(b)
    m.CLK_FREQ = int(1e6)
    platform = Artix7Fast(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL, ]
    )
    installMathLibComponentGenerators(platform)
    print(to_rtl_str(m, target_platform=platform))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpDiv_TC('test_div_py')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpCmp_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

