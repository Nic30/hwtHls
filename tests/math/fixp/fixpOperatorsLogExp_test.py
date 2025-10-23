import math

from hwt.serializer.mode import serializeParamsUniq
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpUnary_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.fixpexp import FixpExp
from tests.math.fixp.fixplog import FixpLog2
from tests.math.hFloatTmp.hFloatTmpOps import exp, log2


@serializeParamsUniq
class TestModuleFixpExp(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return exp(a)


class FixpExp_TC(FixpUnary_TC):
    FP_TY = HFixedPointQ(8, 8, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    RTL_SIM_TIME_MULTIPLIER = 1.2
    MAX_TABLE_ADDR_WIDTH = 8
    # optThroughputVsArea = 0.0
    optThroughputVsArea = 1.0
    INPUT_DATA = (
       0.0,
       1.0,
       2.0,
       3.0,
       4.0,
       0.5,
       0.25,
       0.3,
       -0.5,
       -1.0,
       -2.0,
       )
    MODULE_CLS = TestModuleFixpExp

    def _model(self, a: float) -> float:
        return math.exp(a)

    def test_py(self):
        t = HFixedPointQ(8, 8, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)

        # maxErr = 0.0
        # maxErrPoint = None
        test_data = self.INPUT_DATA
        # scale = 2 ** -8
        # test_data = [scale * (i - 2 ** 8) for i in range(2 ** 16 - 1)]
        fixpexp = FixpExp(t, self.MAX_TABLE_ADDR_WIDTH)
        for x in test_data:
            _x = t.from_py(x)
            res = fixpexp.fixpexp_tabularized(_x)
            err = abs(math.exp(x) - float(res))
            self.assertLessEqual(err, 2 ** -7)
            # if err > maxErr:
            #    maxErr = err
            #    maxErrPoint = x
            # print(x, float(res), math.exp(x), err)

        # print("point:", maxErrPoint, " maxErr:", maxErr, "ref:", math.exp(maxErrPoint),
        #       float(fixpexp.fixpexp_tabularized(t.from_py(maxErrPoint))))


@serializeParamsUniq
class TestModuleFixpLog2(_FixpUnOpTestModule):

    @staticmethod
    def HLS_OP_FN(a):
        return log2(a)


class FixpLog2_TC(FixpUnary_TC):
    FP_TY = HFixedPointQ(8, 8)
    RTL_SIM_TIME_MULTIPLIER = 1.2
    MAX_TABLE_ADDR_WIDTH = 8
    optThroughputVsArea = 0.0

    # scale = 2 ** -8
    # test_data = [i * scale for i in range(1, 2 ** 16)]
    INPUT_DATA = [
        1, 2, 4, 5, 6, 8,
        3,
        15,
        0.125,
        0.25,
        0xff * 2.** -6,
        0.5,
        0.75,
        # 0.01,
        1.5, 5.75,
        2. ** -7,  # 0.0078125
        2. ** -6,  # 0.015625
        2. ** -6 + 2. ** -7,  # 0.0234375
    ]
    MODULE_CLS = TestModuleFixpLog2

    def _model(self, a: float) -> float:
        return math.log2(a)

    def test_py(self):
        T = HFixedPointQ(8, 8)
        # maxErr = 0.0
        # maxErrPoint = None
        fixplog2 = FixpLog2(T, self.MAX_TABLE_ADDR_WIDTH)

        for x in self.INPUT_DATA:
            res = float(fixplog2.fixplog2_tabularized_py(x))
            ref = math.log2(x)
            err = math.fabs(res - ref)
            self.assertLessEqual(err, 2 ** -7)
            # print(f"x:{x:.08f},  log2(x):{ref:.08f}, fixplog2:{res:.08f}, err:{err:.08f}")
            # if err > maxErr:
            #    maxErr = err
            #    maxErrPoint = x

        # if maxErrPoint is not None:
        #    print("point:", maxErrPoint, " maxErr:", maxErr, "ref:", math.log2(maxErrPoint), fixplog2.fixplog2_tabularized_py(maxErrPoint))


class FixpExp_lut7_TC(FixpExp_TC):
    MAX_TABLE_ADDR_WIDTH = 7


class FixpLog2_lut7_TC(FixpLog2_TC):
    MAX_TABLE_ADDR_WIDTH = 7


FixpOpLogExp_TCs = [
    FixpExp_TC,
    FixpExp_lut7_TC,
    FixpLog2_TC,
    FixpLog2_lut7_TC,
]

if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast
    # from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
    # from tests.math.installMathLib import installFpComponentGenerators
    # 
    # m = _FixpUnOpTestModule()
    # m.HLS_OP_FN = log2
    # m.T = HFixedPointQ(2, 10, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    # m.CLK_FREQ = int(70e6)
    # platform = Artix7Fast(
    #   debugFilter=HlsDebugBundle.ALL_RELIABLE,
    #   # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED, ]
    # )
    # installFpComponentGenerators(platform, optThroughputVsArea=1.0, MAX_TABLE_ADDR_WIDTH=10)
    # print(to_rtl_str(m, target_platform=platform))

    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in FixpOpLogExp_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpLog2_TC)
    # suite = unittest.TestSuite([FixpLog2_TC('test_rtl')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
