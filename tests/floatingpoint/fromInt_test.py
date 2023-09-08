#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys

from hwt.hdl.types.defs import BIT
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import int64_t, int16_t
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask, ValidityError, to_signed
from tests.floatingpoint.fptypes import IEEE754Fp64, IEEE754Fp, IEEE754Fp16
from tests.floatingpoint.fromInt import IEEE754FpFromInt


class IEEE754FpFromIntConventor(Unit):

    def _config(self) -> None:
        self.T_IN = Param(int64_t)
        self.T = Param(IEEE754Fp64)

        self.FREQ = Param(int(20e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ

        self.a = HsStructIntf()
        self.a.T = self.T_IN
        self.res = HsStructIntf()._m()
        self.res.T = self.T

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            a = hls.read(self.a)
            res = PyBytecodeInline(IEEE754FpFromInt)(a, IEEE754Fp64 ) # self.T
            hls.write(res, self.res)

    def _impl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class IEEE754FpFromInt_TC(SimTestCase):
    TEST_DATA = [
        0, 1, 2, 3,
        mask(32),
        mask(63),  # max number
        to_signed(mask(64) - mask(63), 64),  # min number
        to_signed(mask(64), 64),  # -1
        to_signed(mask(64) - 1, 64),  # -2
    ]

    @staticmethod
    def model(a: int):
        return float(a)

    def test_py(self):
        for a in self.TEST_DATA:
            # print("in:", a)
            _res = IEEE754FpFromInt(int64_t.from_py(a), IEEE754Fp64)
            try:
                res = IEEE754Fp64.to_py(_res)
            except ValidityError:
                res = None
            # check if conversion from py int to hvalue and to float is correct
            resRef = self.model(a)
            # print(res, resRef, "\n", _res, IEEE754Fp64.from_py(resRef))
            self.assertEqual(res, resRef,
                             msg=(res, _res, 'expected', resRef))

    def test_rlt(self):
        u = IEEE754FpFromIntConventor()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        refRes = []
        for a in self.TEST_DATA:
            u.a._ag.data.append(a)
            _resRef = self.model(a)
            # refRes.append(_resRef)
            _resRef = IEEE754Fp64.from_py(_resRef)
            refRes.append((int(_resRef.mantissa), int(_resRef.exponent), int(_resRef.sign)))

        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        self.runSim((len(self.TEST_DATA) + 1) * int(CLK_PERIOD))

        # res = [IEEE754Fp64.to_py(IEEE754Fp64.from_py({"sign": sign, "exponent": exponent, "mantissa": mantissa}))
        #                             for mantissa, exponent, sign in u.res._ag.data]
        res = u.res._ag.data
        self.assertValSequenceEqual(res, refRes)

        self.rtl_simulator_cls = None


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = IEEE754FpFromIntConventor()
    #u.T_IN = int16_t
    #u.T = IEEE754Fp16
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpFromInt_TC('test_cmp_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpFromInt_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
