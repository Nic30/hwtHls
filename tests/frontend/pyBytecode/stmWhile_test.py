#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.stmWhile import HlsPythonHwWhile0a, \
    HlsPythonHwWhile1, HlsPythonHwWhile2, HlsPythonHwWhile3, HlsPythonHwWhile4, \
    HlsPythonHwWhile5, HlsPythonHwWhile0b, HlsPythonHwWhile0c, \
    PragmaInline_HlsPythonHwWhile5, HlsPythonHwWhile6


class StmWhile_ll_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsPythonHwWhile0_ll(self):
        self._test_ll(HlsPythonHwWhile0)

    def test_HlsPythonHwWhile1_ll(self):
        self._test_ll(HlsPythonHwWhile1)

    def test_HlsPythonHwWhile2_ll(self):
        self._test_ll(HlsPythonHwWhile2)


class StmWhile_sim_TC(BaseIrMirRtl_TC):

    def test_HlsPythonHwWhile0b(self):

        def model(dataOut):
            while True:
                dataOut.append(10)
                yield

        OUT_CNT = 8

        self._testOneOut(HlsPythonHwWhile0b(), model, OUT_CNT,
                         OUT_CNT * 10, OUT_CNT * 10,
                         OUT_CNT * 10, OUT_CNT + 1)

    def test_HlsPythonHwWhile0c(self):

        def model(dataIn, dataOut):
            while True:
                i = uint8_t.from_py(10)
                while True:
                    i += 1
                    dataOut.append(i)
                    if next(dataIn):
                        break

        OUT_CNT = 16
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(OUT_CNT)]
        self._test_OneInOneOut(HlsPythonHwWhile0c(), model, dataIn,
                   OUT_CNT * 20, OUT_CNT * 20,
                   OUT_CNT * 20, OUT_CNT + 2)

    # def test_HlsPythonHwWhile0(self):
    #    self._test(HlsPythonHwWhile0())
    #
    # def test_HlsPythonHwWhile1(self):
    #    self._test(HlsPythonHwWhile1())
    #
    def test_HlsPythonHwWhile2(self):

        def model(dataOut):
            i = uint8_t.from_py(0)
            while True:  # recognized as HW loop because of type
                if i <= 4:
                    dataOut.append(i)
                    yield
                elif i._eq(10):
                    break
                i += 1

            while True:
                dataOut.append(0)
                yield

        OUT_CNT = 16
        self._testOneOut(HlsPythonHwWhile2(), model, OUT_CNT,
                         OUT_CNT * 20, OUT_CNT * 20,
                         OUT_CNT * 20, OUT_CNT + 1)

    def test_HlsPythonHwWhile3(self):

        def model(dataIn, dataOut):
            while True:
                while True:
                    r1 = next(dataIn)
                    if r1 != 1:
                        r2 = next(dataIn)
                        dataOut.append(r2)
                        if r2 != 2:
                            break
                    else:
                        break

                dataOut.append(99)

        IN_CNT = 32
        in_t = Bits(8)
        dataIn = [in_t.from_py(self._rand.getrandbits(2)) for _ in range(IN_CNT)]
        self._test_OneInOneOut(HlsPythonHwWhile3(), model, dataIn)

    def test_HlsPythonHwWhile4(self, uCls=HlsPythonHwWhile4):

        def model(dataIn, dataOut):
            while True:
                data = Bits(8).from_py(None)
                cntr = 8 - 1
                while cntr >= 0:
                    d = next(dataIn)
                    data = Concat(d, data[8:1])  # shift-in data from left
                    cntr = cntr - 1
                dataOut.append(data)

        IN_CNT = 32
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(IN_CNT)]
        self._test_OneInOneOut(uCls(), uCls.model, dataIn)

    def test_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(uCls=HlsPythonHwWhile5)

    def test_HlsPythonHwWhile6(self):
        self.test_HlsPythonHwWhile4(uCls=HlsPythonHwWhile6)

    def test_PragmaInline_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(uCls=PragmaInline_HlsPythonHwWhile5)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([StmWhile_sim_TC("test_HlsPythonHwWhile2")])
    # suite = testLoader.loadTestsFromTestCase(StmWhile_sim_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
