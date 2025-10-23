#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.simulator.simTestCase import SimTestCase
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import to_signed, to_unsigned
from tests.math.componentGenerators._mul.mulSequential import PipelinedMultiplierSequential
from tests.math.componentGenerators._mul.mulTestUtils import _allCombinationsOfValuesForBitewidthsForTy
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class PipelinedMultiplierSequential_4x4u_TC(SimTestCase):
    T = HBits(4)
    RTL_SIM_TIME_MULTIPLIER = T.bit_length()
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]

    def initPlatform(self, target_platform:TestLlvmIrAndMirPlatform):
        pass
        # installFpComponentGenerators(target_platform,
        #                             optThroughputVsArea=self.optThroughputVsArea,
        #                             MAX_TABLE_ADDR_WIDTH=self.MAX_TABLE_ADDR_WIDTH)

    def _model(self, a: int, b: int) -> int:
        res = a * b
        T = self.T
        if T.signed:
            res = to_unsigned(res, T.bit_length())
            res &= T.all_mask()
            res = to_signed(res, T.bit_length())
        else:
            res &= T.all_mask()
        return res

    def _getRefData(self, input_data):
        return [int(self._model(*d)) for d in input_data]

    def prepareDataInFn(self):
        T = self.T
        hasNonBlockingRead = True
        dataIn = []
        for (a, b) in self.INPUT_DATA:
            a = T.from_py(a)
            b = T.from_py(b)
            if hasNonBlockingRead:
                dataIn.append(Concat(b1, b, a))
            else:
                dataIn.append(Concat(b, a))
        return dataIn

    def prepareDataInFnRtl(self):
        T = self.T
        for (a, b) in self.INPUT_DATA:
            a = T.from_py(a)
            b = T.from_py(b)
            yield (a, b)

    def getCheckDataOutFn(self, REF_DATA: list[int]):

        def checkDataOutFn(dataOut: list[HBitsConst]):
            self.assertValSequenceEqual(dataOut, REF_DATA)

        return  checkDataOutFn

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = PipelinedMultiplierSequential()
        dut.T = self.T
        dut.CLK_FREQ = freq
        self._test_rtl(dut, freq, runTestAfterEachPass)

    def _test_rtl(self, dut, freq, runTestAfterEachPass):
        dut.CLK_FREQ = freq
        dut.IN_CHANNEL_TYPE = dut.OUT_CHANNEL_TYPE = HwIOStructRdVld
        REF_DATA = self._getRefData(self.INPUT_DATA)
        target_platform = TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
            self.prepareDataInFn,
            None,  # self.getCheckDataOutFn(REF_DATA),
            None,
            # debugFilter=HlsDebugBundle.ALL_RELIABLE,
            llvmCliArgs=[
            #    LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            ],
            # noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
            runTestAfterEachPass=runTestAfterEachPass,
            # runTestAfterEachMirPass=True,
        )
        self.initPlatform(target_platform)
        self.compileSimAndStart(dut, target_platform=target_platform)
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.data_in._ag.data.extend(self.prepareDataInFnRtl())
        dut.data_in._ag.presetBeforeClk = True
        dut.data_out._ag.presetBeforeClk = True

        self.runSim(int((len(dut.data_in._ag.data) * self.RTL_SIM_TIME_MULTIPLIER + 20) * CLK_PERIOD))

        checkFn = self.getCheckDataOutFn(REF_DATA)
        checkFn(dut.data_out._ag.data)
        self.rtl_simulator_cls = None


class PipelinedMultiplierSequential_4x4s_TC(PipelinedMultiplierSequential_4x4u_TC):
    T = HBits(4, signed=True)
    RTL_SIM_TIME_MULTIPLIER = T.bit_length()
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


class PipelinedMultiplierSequential_2x2u_TC(PipelinedMultiplierSequential_4x4u_TC):
    T = HBits(2)
    RTL_SIM_TIME_MULTIPLIER = T.bit_length()
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


class PipelinedMultiplierSequential_2x2s_TC(PipelinedMultiplierSequential_4x4u_TC):
    T = HBits(2, signed=True)
    RTL_SIM_TIME_MULTIPLIER = T.bit_length()
    INPUT_DATA = [
        *_allCombinationsOfValuesForBitewidthsForTy(T)
    ]


PipelinedMultiplierSequential_TCs = [
    PipelinedMultiplierSequential_2x2u_TC,
    PipelinedMultiplierSequential_4x4u_TC,
    PipelinedMultiplierSequential_2x2s_TC,
    PipelinedMultiplierSequential_4x4s_TC,
]

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpDiv_TC('test_div_py')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in PipelinedMultiplierSequential_TCs])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
