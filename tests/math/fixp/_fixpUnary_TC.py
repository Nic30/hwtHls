#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwModule import HwModule
from hwt.simulator.simTestCase import SimTestCase
from hwtSimApi.utils import freq_to_period
from tests.math.installMathLib import installMathLibComponentGenerators
from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class FixpUnary_TC(SimTestCase):
    FP_TY = HFixedPointQ(4, 8)
    MAX_TABLE_ADDR_WIDTH = 0
    optThroughputVsArea = 0.0
    RTL_SIM_TIME_MULTIPLIER = 1.0
    MODULE_CLS: Type[_FixpUnOpTestModule]

    def initPlatform(self, target_platform:TestLlvmIrAndMirPlatform):
        installMathLibComponentGenerators(target_platform,
                                     optThroughputVsArea=self.optThroughputVsArea,
                                     MAX_TABLE_ADDR_WIDTH=self.MAX_TABLE_ADDR_WIDTH)

    def _model(self, a: float) -> float:
        return self.MODULE_CLS.HLS_OP_FN(a)

    def _getRefData(self, input_data):
        return [self._model(d) for d in input_data]

    def prepareDataInFn(self):
        fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())
        dataIn = []
        for a in self.INPUT_DATA:
            a = fpTy.from_py(a)._reinterpret_cast(bitTy)
            dataIn.append(a)
        return dataIn

    def prepareDataInFnRtl(self):
        fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())
        for a in self.INPUT_DATA:
            a = fpTy.from_py(a)._reinterpret_cast(bitTy)
            yield (a,)

    def getCheckDataOutFn(self, REF_DATA: list[tuple[float, float]], fpTy=None):
        if fpTy is None:
            fpTy = self.FP_TY
        bitTy = HBits(fpTy.bit_length())

        def toFloat(v):
            assert v._dtype.bit_length() == bitTy.bit_length(), (v, bitTy)
            return float(bitTy.from_py(v.val, v.vld_mask)._reinterpret_cast(fpTy)) if v._is_full_valid() else v

        dataOutRef: list[HBitsConst] = []
        for ref in REF_DATA:
            ref = fpTy.from_py(ref)._reinterpret_cast(bitTy)
            dataOutRef.append(int(ref))

        def checkDataOutFn(dataOut):
            self.assertValSequenceEqual(dataOut, dataOutRef, (
                [toFloat(v) for v in dataOut],
                "!=", REF_DATA)
            )

        return  checkDataOutFn

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = self.MODULE_CLS()
        dut.T = self.FP_TY
        dut.CLK_FREQ = freq
        self._test_rtl(dut, runTestAfterEachPass)

    def _test_rtl(self, dut: HwModule, runTestAfterEachPass=False, randomizeIn=False, randomizeOut=False, rtlTimeMultiplier=1):
        REF_DATA = self._getRefData(self.INPUT_DATA)
        target_platform = TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
            self.prepareDataInFn,
            self.getCheckDataOutFn(REF_DATA),
            None,
            topToRunTestsOn=dut,
            # debugFilter=HlsDebugBundle.ALL_RELIABLE,
            # llvmCliArgs=[
            #    LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            # ],
            # noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
            runTestAfterEachPass=runTestAfterEachPass
        )
        self.initPlatform(target_platform)
        self.compileSimAndStart(dut, target_platform=target_platform)
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.data_in._ag.data.extend(self.prepareDataInFnRtl())
        dut.data_in._ag.presetBeforeClk = True
        dut.data_out._ag.presetBeforeClk = True
        if randomizeIn:
            self.randomize(dut.data_in)
        if randomizeOut:
            self.randomize(dut.data_out)

        self.runSim(int((len(dut.data_in._ag.data) * self.RTL_SIM_TIME_MULTIPLIER + 20) * rtlTimeMultiplier * CLK_PERIOD))

        # fpTy = self.FP_TY
        # bitTy = HBits(fpTy.bit_length())

        checkFn = self.getCheckDataOutFn(REF_DATA)
        # def toFloat(v):
        #    return float(bitTy.from_py(v.val, v.vld_mask)._reinterpret_cast(fpTy)) if v._is_full_valid() else v

        # self.assertValSequenceEqual([toFloat(v) for v in dut.data_out._ag.data], REF_DATA)
        checkFn(dut.data_out._ag.data)
        self.rtl_simulator_cls = None
