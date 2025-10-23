#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Tuple

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaFunction import PyBytecodeSkipPass
from hwtHls.netlist.extraOps import OP_UDIVREM
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.math.componentGenerators._div.divRestoring import DivRemHwModule, divremRestoring
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform
from tests.math.installMathLib import installMathLibComponentGenerators


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

    def _getRefData(self, input_data):
        return [self._model(*d) for d in input_data]

    def _model(self, dividend: int, divisor: int, isSigned:bool) -> Tuple[int, int]:
        if isSigned:
            raise NotImplementedError()

        quotient = dividend // divisor
        remainder = dividend % divisor
        return quotient, remainder

    def test_div_py(self):
        T = HBits(self.DATA_WIDTH)
        divFn = self.HLS_DIV_FN
        for (dividend, divisor, isSigned) in self.INPUT_DATA:
            _dividend = T.from_py(dividend)
            _divisor = T.from_py(divisor)
            _isSigned = BIT.from_py(isSigned)
            (quotient, remainder) = self._model(dividend, divisor, isSigned)
            _quotient, _remainder = divFn(_dividend, _divisor, _isSigned)
            self.assertValSequenceEqual([_quotient, _remainder], (quotient, remainder),
                                        msg=((dividend, "//", divisor, "signed?:", isSigned), (quotient, "rem:", remainder)))

    def prepareDataInFn(self):
        T = HBits(self.DATA_WIDTH)
        dataIn = []
        for (dividend, divisor, isSigned) in self.INPUT_DATA:
            _dividend = T.from_py(dividend)
            _divisor = T.from_py(divisor)
            _isSigned = BIT.from_py(isSigned)
            dataIn.append(Concat(_isSigned, _divisor, _dividend))
        return dataIn

    def getCheckDataOutFn(self, REF_DATA):
        DW = self.DATA_WIDTH

        dataOutRef = []
        for (quotient, remainder) in REF_DATA:
            dataOutRef.append((remainder << DW) | quotient)

        def checkDataOutFn(dataOut):

            self.assertValSequenceEqual(dataOut, dataOutRef, "[%s] != [%s]" % (
                ", ".join("(q:%d, r:%d)" % (int(i) & mask(DW), int(i) >> DW) if i._is_full_valid() else repr(i) for i in dataOut),
                ", ".join("(q:%d, r:%d)" % (q, r) for q, r in REF_DATA)
            ))

        return  checkDataOutFn

    def platformSetUp(self, p: TestLlvmIrAndMirPlatform):
        installMathLibComponentGenerators(p)

    def test_div_rtl(self, MAIN_FN_META=None, randomizeIn=False, randomizeOut=False, runTestAfterEachPass=False):
        dut = DivRemHwModule()
        dut.T = HBits(self.DATA_WIDTH)
        dut.FN = self.HLS_DIV_FN
        dut.MAIN_FN_META = MAIN_FN_META
        dut.UNROLL_FACTOR = self.UNROLL_FACTOR
        dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        dut.CHECK_FOR_INEFFICIENCY = False
        REF_DATA = self._getRefData(self.INPUT_DATA)
        p = TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
            self.prepareDataInFn,
            self.getCheckDataOutFn(REF_DATA),
            None,
            topToRunTestsOn=dut,
            # debugFilter=HlsDebugBundle.ALL_RELIABLE,
            # llvmCliArgs=[
            #    LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            # ],
            # noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
            runTestAfterEachPass=runTestAfterEachPass,
        )
        self.platformSetUp(p)
        self.compileSimAndStart(dut, target_platform=p)
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.data_in._ag.data.extend(self.INPUT_DATA)
        dut.data_in._ag.presetBeforeClk = True
        dut.data_out._ag.presetBeforeClk = True

        timeMultiplier = 1
        if randomizeIn:
            self.randomize(dut.data_in)
            timeMultiplier *= 2
        if randomizeOut:
            self.randomize(dut.data_out)
            timeMultiplier *= 2
        self.runSim((len(dut.data_in._ag.data) * dut.T.bit_length() + 20) * int(CLK_PERIOD) * timeMultiplier)
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        self.assertValSequenceEqual(dut.data_out._ag.data, REF_DATA)
        self.rtl_simulator_cls = None

    def test_div_no_SlicesToIndependentVariablesPass(self):
        self.test_div_rtl(MAIN_FN_META=PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass"]),
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
    """

    @staticmethod
    @hlsBytecode
    def HLS_DIV_FN(dividend, divisor, isSigned, loopPragmaGetter=None):
        quotient = dividend // divisor
        remainder = dividend % divisor  # [fixme] rem vs mod
        return quotient, remainder

    def platformSetUp(self, p:TestLlvmIrAndMirPlatform):
        installMathLibComponentGenerators(p)
        p._componentGenerators[OP_UDIVREM].optThroughputVsArea = self.UNROLL_FACTOR / self.DATA_WIDTH


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
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = DivRemHwModule()
    m.T = HBits(4, False)
    m.FN = DivRemRestoringGen_TC.HLS_DIV_FN
    # m.UNROLL_FACTOR = 1
    m.CLK_FREQ = int(200e6)
    m.IN_CHANNEL_TYPE = HwIOStructRdVld
    m.MAIN_FN_META = PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass"])
    p = Artix7Fast(
      debugFilter=HlsDebugBundle.ALL_RELIABLE,
      # llvmCliArgs=[
      #   LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
      #   LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
      # ]
    )
    installMathLibComponentGenerators(p)
    p._componentGenerators[OP_UDIVREM].optThroughputVsArea = 0  # 2 / m.T.bit_length()
    # print(to_rtl_str(m, target_platform=p))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([DivRemRestoringGen_TC('test_div_no_SlicesToIndependentVariablesPass')])
    suite = unittest.TestSuite(testLoader.loadTestsFromTestCase(cls) for cls in DivRemRestoring_TCs)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
