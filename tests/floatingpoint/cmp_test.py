#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.floatingpoint.cmp import IEEE754FpCmp, IEEE754FpCmpResult
from tests.floatingpoint.fptypes import IEEE754Fp32
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class IEEE754FpComparator(Unit):

    def _config(self) -> None:
        self.T = Param(IEEE754Fp32)
        self.FREQ = Param(int(20e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ

        self.a = HsStructIntf()
        self.b = HsStructIntf()
        self.a.T = self.b.T = self.T

        self.res = Handshaked()._m()
        self.res.DATA_WIDTH = 2

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            a = hls.read(self.a)
            b = hls.read(self.b)
            res = PyBytecodeInline(IEEE754FpCmp)(a, b)
            hls.write(res, self.res)

    def _impl(self) -> None:
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
        u = IEEE754FpComparator()
        refRes = []
        aDataIn = []
        bDataIn = []
        for (a, b) in self.TEST_DATA_FORMATED:
            aDataIn.append(a)
            bDataIn.append(b)
            _a = IEEE754Fp32.to_py(a)
            _b = IEEE754Fp32.to_py(b)
            _resRef = int(self.model(_a, _b))
            refRes.append(_resRef)

        def prepareDataInFn():
            aDataIn = []
            bDataIn = []
            t = Bits(u.T.bit_length())
            for a, b in self.TEST_DATA:
                aDataIn.append(t.from_py(a))
                bDataIn.append(t.from_py(b))

            return aDataIn, bDataIn

        def checkDataOutFn(dataOut):
            self.assertValSequenceEqual(dataOut, refRes)

        self.compileSimAndStart(u, target_platform=TestLlvmIrAndMirPlatform.forSimpleDataInDataOutUnit(
                                    prepareDataInFn, checkDataOutFn, None,
                                    inputCnt=2,
                                    noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
                                    # runTestAfterEachPass=True
                                    ))

        u.a._ag.data.extend(aDataIn)
        u.b._ag.data.extend(bDataIn)

        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        self.runSim((len(self.TEST_DATA_FORMATED) + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.res._ag.data, refRes,
                                    [(IEEE754Fp32.to_py(a), IEEE754Fp32.to_py(b), a, b)
                                     for a, b in self.TEST_DATA_FORMATED])
        self.rtl_simulator_cls = None


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = IEEE754FpComparator()

    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpCmp_TC('test_cmp_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpCmp_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
