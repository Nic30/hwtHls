#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pragmaFunction import PyBytecodeSkipPass
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.netlist.extraOps import OP_UDIVREM
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
from hwtHls.platform.virtual import VirtualHlsPlatform
from pyMathBitPrecise.bit_utils import mask
from tests.math.componentGenerators._div.divRestoring import DivRemHwModule, divremRestoring
from tests.math.installMathLib import installMathLibComponentGenerators
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIoStruct import PassTestIoInStruct, PassTestIoOutStruct


class PassTestInjectorForDivRemRestoring(PassTestInjectorForDInDOutHwModule):

    @override
    def checkDataOutFn(self, dataOut):
        DW = self._topToRunTestsOn.DATA_WIDTH
        self.assertValSequenceEqual(dataOut, self.OUT_DATA_REF[0], "[%s] != [%s]" % (
            ", ".join("(q:%d, r:%d)" % (int(i) & mask(DW), int(i) >> DW) if i._is_full_valid() else repr(i) for i in dataOut),
            ", ".join("(q:%d, r:%d)" % (q, r) for q, r in self.OUT_DATA_REF_PY[0])
        ))


class DivRemRestoring_TC(SimTestCase):
    DATA_WIDTH = 4
    UNROLL_FACTOR = 1
    INPUT_DATA = [
        # dividend, divisor, isSigned
        (1, 1, 0),
        (2, 2, 0),
        (4, 2, 0),
        (13, 3, 0),
        (3, 15, 0),
        (9, 3, 0)
    ]

    HLS_DIV_FN = staticmethod(divremRestoring)

    def platformSetUp(self, p: VirtualHlsPlatform):
        pass

    def test_div_py(self):
        T = HBits(self.DATA_WIDTH)
        divFn = self.HLS_DIV_FN
        for (dividend, divisor, isSigned) in self.INPUT_DATA:
            _dividend = T.from_py(dividend)
            _divisor = T.from_py(divisor)
            _isSigned = BIT.from_py(isSigned)
            (quotient, remainder) = DivRemHwModule.model(dividend, divisor, isSigned)
            _quotient, _remainder = divFn(_dividend, _divisor, _isSigned)
            self.assertValSequenceEqual([_quotient, _remainder], (quotient, remainder),
                                        msg=((dividend, "//", divisor, "signed?:", isSigned), (quotient, "rem:", remainder)))

    def test_div_rtl(self,
                     MAIN_FN_META=None,
                     randomizeIn=False,
                     randomizeOut=False,
                     runTestAfterEachPass=False):
        dut = DivRemHwModule()
        dut.T = HBits(self.DATA_WIDTH)
        dut.FN = self.HLS_DIV_FN
        dut.MAIN_FN_META = MAIN_FN_META
        dut.UNROLL_FACTOR = self.UNROLL_FACTOR
        dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        dut.CHECK_FOR_INEFFICIENCY = False
        # dut.CLK_FREQ = int(200e6)

        platform = VirtualHlsPlatform(
                                      # debugFilter=HlsDebugBundle.ALL_RELIABLE,
                                      llvmCliArgs=[
                                          LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                                          # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                                      ],
                                      )

        passTests = PassTestInjectorForDivRemRestoring(dut, self)
        self.platformSetUp(platform)
        passTests.setRunTestsAfter(runTestAfterEachPass=runTestAfterEachPass)

        timeMultiplier = 1
        if randomizeIn:
            timeMultiplier *= 2
        if randomizeOut:
            timeMultiplier *= 2
        inT, outT = dut._getDataInOutTypes()
        passTests.setTimeLimits(wallTimeRtl=(len(self.INPUT_DATA) * dut.T.bit_length() + 20) * timeMultiplier)
        passTests.test_allInOne_withModel(
            (PassTestIoInStruct(inT, self.INPUT_DATA, name="data_in", inInPyFormat=True, unpackMembersForModel=True, randomizeControl=randomizeIn),),
            OUT_DATA_REF=(PassTestIoOutStruct(outT, (), name="data_out", randomizeControl=randomizeOut),),
            platform=platform,
        )

        self.rtl_simulator_cls = None

    def test_div_no_SlicesToIndependentVariablesPass(self):
        self.test_div_rtl(MAIN_FN_META=PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass"]),
                          runTestAfterEachPass=False)

    def test_div_no_SelectPruningPass(self):
        self.test_div_rtl(MAIN_FN_META=PyBytecodeSkipPass(["hwtHls::SelectPruningPass"]),
                          runTestAfterEachPass=False)

    def test_div_no_SlicesToIndependentVariablesPassAndSelectPruningPass(self):
        self.test_div_rtl(MAIN_FN_META=PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass", "hwtHls::SelectPruningPass"]),
                          runTestAfterEachPass=False)

    def test_div_rtl_inRand(self):
        self.test_div_rtl(randomizeIn=True, randomizeOut=False)

    def test_div_rtl_inoutRand(self):
        self.test_div_rtl(randomizeIn=True, randomizeOut=True)

    def test_div_rtl_outRand(self):
        self.test_div_rtl(randomizeIn=False, randomizeOut=True)


class DivRemRestoring_unroll2_TC(DivRemRestoring_TC):
    UNROLL_FACTOR = 2


class DivRemRestoring_unroll4_TC(DivRemRestoring_TC):
    UNROLL_FACTOR = 4


class DivRemRestoringGen_TC(DivRemRestoring_TC):
    """
    Variant of DivRestoring_TC which test default component generator for / and % operator installed in Platform
    (the DivRemRestoring is instanciated by this operator)
    """

    @staticmethod
    @hlsBytecode
    def HLS_DIV_FN(dividend, divisor, isSigned, loopPragmaGetter=None):
        quotient = dividend // divisor
        remainder = dividend % divisor  # [fixme] rem vs mod
        return quotient, remainder

    def platformSetUp(self, p:VirtualHlsPlatform):
        installMathLibComponentGenerators(p)
        gen = p._componentGenerators[OP_UDIVREM]
        gen.optThroughputVsArea = self.UNROLL_FACTOR / self.DATA_WIDTH
        gen.CHECK_FOR_INEFFICIENCY = False


class DivRemRestoringGen_unroll2_TC(DivRemRestoringGen_TC):
    UNROLL_FACTOR = 2


class DivRemRestoringGen_unroll4_TC(DivRemRestoringGen_TC):
    UNROLL_FACTOR = 4


DivRemRestoring_TCs = [
    DivRemRestoring_TC,
    DivRemRestoring_unroll2_TC,
    DivRemRestoring_unroll4_TC,
    DivRemRestoringGen_TC,
    DivRemRestoringGen_unroll2_TC,
    DivRemRestoringGen_unroll4_TC,
]

if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast

    # m = DivRemHwModule()
    # m.T = HBits(4, False)
    # m.FN = DivRemRestoringGen_TC.HLS_DIV_FN
    # m.CLK_FREQ = int(1e6)
    # m.UNROLL_FACTOR = 4
    # m.CHECK_FOR_INEFFICIENCY = False
    # # m.CLK_FREQ = int(200e6)
    # m.IN_CHANNEL_TYPE = HwIOStructRdVld
    # # m.MAIN_FN_META = PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass"])
    # p = Artix7Fast(
    #  debugFilter=HlsDebugBundle.ALL_RELIABLE,
    #  llvmCliArgs=[
    #    # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
    #    # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
    #    # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
    #    # LLVM_CLI_COMMON_OPTS.printBefore("hwtHls::TrivialSimplifyCFGPass"),
    #    # LLVM_CLI_COMMON_OPTS.printAfter("hwtHls::TrivialSimplifyCFGPass"),
    #    # LLVM_CLI_COMMON_OPTS.printBefore("hwtHls::HwtHlsInstCombinePass"),
    #    # LLVM_CLI_COMMON_OPTS.printAfter("hwtHls::HwtHlsInstCombinePass"),
    #    # LLVM_CLI_COMMON_OPTS.printBefore("simplifycfg"),
    #    # LLVM_CLI_COMMON_OPTS.printAfter("simplifycfg"),
    #    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
    #  ]
    # )
    # installMathLibComponentGenerators(p)
    # p._componentGenerators[OP_UDIVREM].optThroughputVsArea = 0  # 2 / m.T.bit_length()
    # print(to_rtl_str(m, target_platform=p))

    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite(testLoader.loadTestsFromTestCase(cls) for cls in DivRemRestoring_TCs)
    # suite = unittest.TestSuite([DivRemRestoring_TC('test_div_no_SlicesToIndependentVariablesPassAndSelectPruningPass')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
