#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpAdd_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpCmpOpTestModule
from hwt.serializer.mode import serializeParamsUniq


@serializeParamsUniq
class TestModuleFixpCmp_OLT(_FixpCmpOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a < b


class FixpCmp_OLT_TC(FixpAdd_TC):
    FP_TY = HFixedPointQ(3, 4)
    MODULE_CLS = TestModuleFixpCmp_OLT

    def _model(self, a: float, b: float) -> bool:
        return int(self.MODULE_CLS.HLS_OP_FN(a, b))  # int to have visually shorter output

    def getCheckDataOutFn(self, REF_DATA):

        def checkDataOutFn(dataOut):
            self.assertValSequenceEqual(dataOut, REF_DATA)

        return  checkDataOutFn


@serializeParamsUniq
class TestModuleFixpCmp_OLE(_FixpCmpOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a <= b


class FixpCmp_OLE_TC(FixpCmp_OLT_TC):
    MODULE_CLS = TestModuleFixpCmp_OLE


@serializeParamsUniq
class TestModuleFixpCmp_OEQ(_FixpCmpOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a._eq(b)


class FixpCmp_OEQ_TC(FixpCmp_OLT_TC):
    MODULE_CLS = TestModuleFixpCmp_OEQ

    def _model(self, a: float, b: float) -> bool:
        return int(a == b)  # int to have visually shorter output


@serializeParamsUniq
class TestModuleFixpCmp_ONE(_FixpCmpOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a != b


class FixpCmp_ONE_TC(FixpCmp_OLT_TC):
    MODULE_CLS = TestModuleFixpCmp_ONE


@serializeParamsUniq
class TestModuleFixpCmp_OGT(_FixpCmpOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a > b


class FixpCmp_OGT_TC(FixpCmp_OLT_TC):
    MODULE_CLS = TestModuleFixpCmp_OGT


@serializeParamsUniq
class TestModuleFixpCmp_OGE(_FixpCmpOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a >= b


class FixpCmp_OGE_TC(FixpCmp_OLT_TC):
    MODULE_CLS = TestModuleFixpCmp_OGE


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

    m = TestModuleFixpCmp_OEQ()
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

