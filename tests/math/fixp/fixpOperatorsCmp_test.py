#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from tests.math.fixp._fixpAlu2_TC import FixpAlu2_TC
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpAdd_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpCmpOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps
from tests.passTestIo import PassTestIoOut


@serializeParamsUniq
class TestModuleFixpCmp_OLT(_FixpCmpOpTestModule):

    @staticmethod
    def HLS_OP_FN(a, b):
        return a < b


class FixpCmp_OLT_TC(FixpAdd_TC):
    FP_TY = HFixedPointQ(3, 4)
    MODULE_CLS = TestModuleFixpCmp_OLT

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        FixpAlu2_TC.test_rtl(self, runTestAfterEachPass, freq=freq,
                               OUT_DATA_REF=(PassTestIoOut([], name="data_out"),))


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

    @override
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True, inputArgsAreStructMembers=True)
    def model(self, a: float, b: float) -> bool:
        return int(a == b)  # int to have visually shorter output


class FixpCmp_OEQ_TC(FixpCmp_OLT_TC):
    MODULE_CLS = TestModuleFixpCmp_OEQ


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

