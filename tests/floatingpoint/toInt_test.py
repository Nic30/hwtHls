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
from hwtLib.types.ctypes import int64_t
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask, ValidityError, to_signed
from tests.floatingpoint.fptypes import IEEE754Fp64
from tests.floatingpoint.toInt import IEEE754FpToInt


class IEEE754FpToIntConventor(Unit):

    def _config(self) -> None:
        self.T = Param(IEEE754Fp64)
        self.FREQ = Param(int(20e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ

        self.a = HsStructIntf()
        self.a.T = self.T
        self.res = HsStructIntf()._m()
        self.res.T = int64_t

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            a = hls.read(self.a)
            res = self.res.T.from_py(None)
            PyBytecodeInline(IEEE754FpToInt)(a, res)
            hls.write(res, self.res)

    def _impl(self) -> None:
        hls = HlsScope(self)
        assert sys.float_info.mant_dig - 1 == self.T.MANTISSA_WIDTH, (sys.float_info.mant_dig, self.T.MANTISSA_WIDTH)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class IEEE754FpToInt_TC(SimTestCase):
    TEST_DATA = [float(n) for n in [
        0.1,
        0, 1, 2, 3,
        mask(32),
        mask(63),
        mask(64) - mask(63),
        mask(64),
        -1,
        -0.1,
        -mask(63),
    ]]

    @staticmethod
    def model(a: float):
        res = int(a)
        return max(min(res, mask(64 - 1)), to_signed(1 << 63, 64))

    def test_py(self):
        resV = int64_t.from_py(None)
        for a in self.TEST_DATA:
            _a = IEEE754Fp64.from_py(a)
            _res = IEEE754FpToInt(_a, resV)
            try:
                res = int(_res)
            except ValidityError:
                res = None
            # check if conversion from py int to hvalue and to float is correct
            resRef = self.model(a)
            self.assertEqual(res, resRef, msg=(res, _res, 'expected', resRef, "input", a))

    def test_rtl(self):
        u = IEEE754FpToIntConventor()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        refRes = []
        for a in self.TEST_DATA:
            _a = IEEE754Fp64.from_py(a)
            u.a._ag.data.append(_a)
            _resRef = int(self.model(a))
            refRes.append(_resRef)

        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        self.runSim((len(self.TEST_DATA) + 1) * 32 * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.res._ag.data, refRes,
                                    [float(a) for a in self.TEST_DATA])
        self.rtl_simulator_cls = None


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = IEEE754FpToIntConventor()

    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpCmp_TC('test_cmp_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpToInt_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
