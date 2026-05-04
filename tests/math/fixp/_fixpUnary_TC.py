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
from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
from pyMathBitPrecise.bit_utils import mask, to_signed


class FixpUnary_TC(SimTestCase):
    FP_TY = HFixedPointQ(4, 8)
    MAX_TABLE_ADDR_WIDTH = 0
    optThroughputVsArea = 0.0
    RTL_SIM_TIME_MULTIPLIER = 1.0
    MODULE_CLS: Type[_FixpUnOpTestModule]
    MAX_ULP = 1

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
            if self.MAX_ULP < 1:
                maxErrInt = 0
            else:
                maxErrInt = mask(self.MAX_ULP)
            signed = self.FP_TY.signed
            w = self.FP_TY.bit_length()
            if len(dataOut) == len(dataOutRef):
                for i, (res, refInt, refFloat) in enumerate(zip(dataOut, dataOutRef, REF_DATA)):
                    msg = (i, toFloat(res), refFloat)
                    if res._is_full_valid():
                        if signed:
                            res = to_signed(int(res), w)
                            refInt = to_signed(refInt, w)
                        self.assertAlmostEqual(int(res), refInt, delta=maxErrInt, msg=msg)
                    else:
                        self.assertValEqual(res, refInt, msg=msg)
            else:
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

    def _test_rtl(self, dut: HwModule, runTestAfterEachPass=False,
                  randomizeIn=False, randomizeOut=False, rtlTimeMultiplier=1):
        REF_DATA = self._getRefData(self.INPUT_DATA)
        checkFn = self.getCheckDataOutFn(REF_DATA)
        target_platform = TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
            self.prepareDataInFn,
            checkFn,
            None,
            topToRunTestsOn=dut,
            #debugFilter={*HlsDebugBundle.ALL_RELIABLE,
            #              HlsDebugBundle.DBG_4_0_hwscheduleTrace,
            #              HlsDebugBundle.DBG_4_0_hwscheduleDumpAfterPhases,
            #              HlsDebugBundle.DBG_4_0_hwschedulePrintPhaseBoundaries,
            #              HlsDebugBundle.DBG_4_0_addSignalNamesToData,
            #              HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
            #            },
            # llvmCliArgs=[
            #    # LLVM_CLI_COMMON_OPTS.VREGIFCVT_TRACE,
            #    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
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

        # def toFloat(v):
        #    return float(bitTy.from_py(v.val, v.vld_mask)._reinterpret_cast(fpTy)) if v._is_full_valid() else v

        # self.assertValSequenceEqual([toFloat(v) for v in dut.data_out._ag.data], REF_DATA)
        checkFn(dut.data_out._ag.data)
        self.rtl_simulator_cls = None
