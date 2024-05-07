#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import nan, inf
from itertools import zip_longest
from math import isnan
import struct
import sys



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
from tests.floatingpoint.add import IEEE754FpAdd
from tests.floatingpoint.cmp import IEEE754FpCmp, IEEE754FpCmpResult
from tests.floatingpoint.cmp_test import IEEE754FpComparator
from tests.floatingpoint.fptypes import IEEE754Fp32, IEEE754Fp64, IEEE754Fp
from tests.floatingpoint.fptypes_test import fp64reinterpretToInt, \
    int64reinterpretToFloat
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class IEEE754FpAdder(Unit):

    def _config(self) -> None:
        self.T = Param(IEEE754Fp64)
        self.FREQ = Param(int(20e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ

        self.a = HsStructIntf()
        self.b = HsStructIntf()
        self.res = HsStructIntf()._m()
        self.a.T = self.b.T = self.res.T = self.T

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            a = hls.read(self.a).data
            b = hls.read(self.b).data
            res = PyBytecodeInline(IEEE754FpAdd)(a, b)
            hls.write(res, self.res)

    def _impl(self) -> None:
        IEEE754FpComparator._impl(self)


class IEEE754FpAdder_TC(SimTestCase):
    TEST_DATA = [
        (1.0, 1.0),
        (1.125, 1.0),
        (1.25, 1.0),
        (1.0, 2.0),
        (1.0, 2.25),
        (nan, 1.0),
        (inf, 1.0),
        (-inf, 1.0),
        (inf, nan),
        (sys.float_info.max, 1.0),
        (sys.float_info.epsilon, sys.float_info.epsilon),
    ]

    TEST_DATA_FORMATED = [
       (IEEE754Fp64.from_py(aF), IEEE754Fp64.from_py(bF)) for aF, bF in TEST_DATA
    ]

    @staticmethod
    def model(a: float, b: float):
        return a + b

    def test_add_py(self):
        t: IEEE754Fp = self.TEST_DATA_FORMATED[0][0]._dtype
        for (a, b), (aRaw, bRaw) in zip(self.TEST_DATA_FORMATED, self.TEST_DATA):
            resRef = self.model(aRaw, bRaw)
            res = IEEE754FpAdd(a, b, isSim=True)
            # print(aRaw, "+", bRaw, "=", t.to_py(res), "(", resRef, ")")
            msg = ("aRaw", aRaw, "bRaw", bRaw, "a", a, "b", b,
                  'got', res, "expected", t.from_py(resRef))

            if isnan(resRef):
                self.assertTrue(isnan(t.to_py(res)), msg)
            else:
                self.assertEqual(t.to_py(res), resRef,
                                   msg=msg)

    def test_add(self):
        u = IEEE754FpAdder()

        def prepareDataInFn():
            aDataIn = []
            bDataIn = []
            flatTy = Bits(u.T.bit_length())
            for a, b in self.TEST_DATA:
                aDataIn.append(flatTy.from_py(fp64reinterpretToInt(a)))
                bDataIn.append(flatTy.from_py(fp64reinterpretToInt(b)))

            return aDataIn, bDataIn

        refRes = []
        for (a, b) in self.TEST_DATA:
            _resRef = self.model(a, b)
            refRes.append(_resRef)

        def checkDataOutFn(dataOut):
            for i, (ref, d) in enumerate(zip_longest(refRes, dataOut)):
                self.assertIsNotNone(ref, ("Output data contains more data then was expected", dataOut[len(refRes):]))
                self.assertIsNotNone(d, ("Output data is missing data", refRes[len(dataOut):]))
                v = int64reinterpretToFloat(int(d))
                if isnan(ref):
                    self.assertTrue(isnan(v), ref)
                else:
                    self.assertEqual(v, ref, i)

        self.compileSimAndStart(u, target_platform=TestLlvmIrAndMirPlatform.forSimpleDataInDataOutUnit(
                                    prepareDataInFn, checkDataOutFn, None,
                                    inputCnt=2,
                                    noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
                                    # runTestAfterEachPass=True
                                    ))

        aDataIn, bDataIn = prepareDataInFn()
        u.a._ag.data.extend(aDataIn)
        u.b._ag.data.extend(bDataIn)

        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        self.runSim((len(self.TEST_DATA_FORMATED) + 1) * int(CLK_PERIOD))

        self.assertSequenceEqual([int64reinterpretToFloat(int(d)) for d in  u.res._ag.data], refRes,
                                    [(IEEE754Fp64.to_py(a), IEEE754Fp64.to_py(b), a, b)
                                     for a, b in self.TEST_DATA_FORMATED])
        self.rtl_simulator_cls = None


if __name__ == "__main__":
    #from hwt.synthesizer.utils import to_rtl_str
    #from hwtHls.platform.platform import HlsDebugBundle
    #u = IEEE754FpAdder()
    #
    #print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpAdder_TC('test_add_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpAdder_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
