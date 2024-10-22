#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Tuple, Callable

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.floatingpoint.cmp import IEEE754FpCmp, IEEE754FpCmpResult
from tests.floatingpoint.fptypes import IEEE754Fp32, IEEE754Fp
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class IEEE754FpComparator(HwModule):

    def hwConfig(self) -> None:
        self.T = HwParam(IEEE754Fp32)
        self.FREQ = HwParam(int(20e6))

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ

        self.a = HwIOStructRdVld()
        self.b = HwIOStructRdVld()
        self.a.T = self.b.T = self.T

        self.res = HwIODataRdVld()._m()
        self.res.DATA_WIDTH = 2

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            a = hls.read(self.a)
            b = hls.read(self.b)
            res = PyBytecodeInline(IEEE754FpCmp)(a, b)
            hls.write(res, self.res)

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class IEEE754FpCmp_TC(SimTestCase):
    TEST_DATA = [
        (0x40c7ae14, 0x4048f5c3),  # 6.239999771118164   GT 3.140000104904175
        (0xc144cccd, 0xc1566666),  # -12.300000190734863 GT -13.399999618530273
        (0x4174cccd, 0x40133333),  # 15.300000190734863  GT 2.299999952316284
        (0x4144cccd, 0x4164cccd),  # 12.300000190734863  LT 14.300000190734863
        (0xc059999a, 0xc1840000),  # -3.4000000953674316 GT -16.5
        (0xbfa66666, 0x40133333),  # -1.2999999523162842 LT 2.299999952316284
        (0x4154cccd, 0xc164cccd),  # 13.300000190734863  GT -14.300000190734863
        (0x40c7ae14, 0x40c7ae14),  # 6.239999771118164   EQ 6.239999771118164
        (0x4174cccd, 0x4174cccd),  # 15.300000190734863  EQ 15.300000190734863
    ]

    TEST_DATA_FORMATED = [
       (IEEE754Fp32.fromPyInt(aInt), IEEE754Fp32.fromPyInt(bInt)) for aInt, bInt in TEST_DATA
    ]

    @staticmethod
    def model(a: float, b: float):
        if a == b:
            return IEEE754FpCmpResult.EQ
        elif a < b:
            return IEEE754FpCmpResult.LT
        elif a > b:
            return IEEE754FpCmpResult.GT
        else:
            return IEEE754FpCmpResult.UNKNOWN

    @staticmethod
    def prepareTestDataAndRef(TEST_DATA_FORMATED: List[Tuple[IEEE754Fp32, IEEE754Fp32]], model: Callable[[float, float], int]):
        aDataIn = []
        bDataIn = []
        resRef = []
        for (a, b) in TEST_DATA_FORMATED:
            aDataIn.append(a)
            bDataIn.append(b)
            _a = IEEE754Fp32.to_py(a)
            _b = IEEE754Fp32.to_py(b)
            _resRef = int(model(_a, _b))
            resRef.append(_resRef)
        return aDataIn, bDataIn, resRef

    @staticmethod
    def getPrepareDataFnForIRSim(TEST_DATA: List[Tuple[int, int]], fpTy:IEEE754Fp):

        def prepareDataInFn():
            aDataIn = []
            bDataIn = []
            t = HBits(fpTy.bit_length())
            for a, b in TEST_DATA:
                aDataIn.append(t.from_py(a))
                bDataIn.append(t.from_py(b))

            return aDataIn, bDataIn

        return prepareDataInFn

    def test_cmp_py(self):
        for (a, b) in self.TEST_DATA_FORMATED:
            res = IEEE754FpCmp(a, b)
            _a = IEEE754Fp32.to_py(a)
            _b = IEEE754Fp32.to_py(b)
            # check if conversion from py int to hvalue and to float is correct
            resRef = self.model(_a, _b)
            self.assertValEqual(res, int(resRef),
                                msg=(_a, IEEE754FpCmpResult.toStr(res), _b, 'expected', IEEE754FpCmpResult.toStr(resRef)))

    def test_cmp(self):
        dut = IEEE754FpComparator()

        prepareDataInFn = self.getPrepareDataFnForIRSim(self.TEST_DATA, dut.T)
        aDataIn, bDataIn, resRes = self.prepareTestDataAndRef(self.TEST_DATA_FORMATED, self.model)

        def checkDataOutFn(dataOut):
            self.assertValSequenceEqual(dataOut, resRes)

        self.compileSimAndStart(dut, target_platform=TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
                                    prepareDataInFn, checkDataOutFn, None,
                                    inputCnt=2,
                                    noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
                                    # runTestAfterEachPass=True
                                    ))

        dut.a._ag.data.extend(aDataIn)
        dut.b._ag.data.extend(bDataIn)

        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        self.runSim((len(self.TEST_DATA_FORMATED) + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.res._ag.data, resRes,
                                    [(IEEE754Fp32.to_py(a), IEEE754Fp32.to_py(b), a, b)
                                     for a, b in self.TEST_DATA_FORMATED])
        self.rtl_simulator_cls = None


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = IEEE754FpComparator()

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpCmp_TC('test_cmp_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpCmp_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
