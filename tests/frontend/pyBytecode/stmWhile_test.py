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
    PragmaInline_HlsPythonHwWhile5, HlsPythonHwWhile6, MovingOneGen, \
    LoopCondBitSet, LoopZeroPadCompareShift


class StmWhile_ll_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsPythonHwWhile0a_ll(self):
        self._test_ll(HlsPythonHwWhile0a)

    def test_HlsPythonHwWhile1_ll(self):
        self._test_ll(HlsPythonHwWhile1)

    def test_HlsPythonHwWhile2_ll(self):
        self._test_ll(HlsPythonHwWhile2)


class StmWhile_sim_TC(BaseIrMirRtl_TC):

    def test_HlsPythonHwWhile0a(self):
        OUT_CNT = 16
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(OUT_CNT)]
        self._test_OneInOneOut(HlsPythonHwWhile0a(), HlsPythonHwWhile0a.model, dataIn,
                   OUT_CNT * 20, OUT_CNT * 20,
                   OUT_CNT * 20, OUT_CNT + 2)

    def test_HlsPythonHwWhile0b(self):
        OUT_CNT = 8
        self._testOneOut(HlsPythonHwWhile0b(), HlsPythonHwWhile0b.model, OUT_CNT,
                         OUT_CNT * 10, OUT_CNT * 10,
                         OUT_CNT * 10, OUT_CNT + 1)

    def test_HlsPythonHwWhile0c(self):
        OUT_CNT = 16
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(OUT_CNT)]
        self._test_OneInOneOut(HlsPythonHwWhile0c(), HlsPythonHwWhile0c.model, dataIn,
                   OUT_CNT * 20, OUT_CNT * 20,
                   OUT_CNT * 20, OUT_CNT + 2)

    def test_HlsPythonHwWhile1(self):
        OUT_CNT = 16
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(OUT_CNT)]
        self._test_OneInOneOut(HlsPythonHwWhile1(), HlsPythonHwWhile1.model, dataIn,
                         OUT_CNT * 10, OUT_CNT * 10,
                         OUT_CNT * 10, OUT_CNT + 1 + 1,
                         freq=int(50e6))

    def test_HlsPythonHwWhile2(self):
        OUT_CNT = 16
        self._testOneOut(HlsPythonHwWhile2(), HlsPythonHwWhile2.model, OUT_CNT,
                         OUT_CNT * 20, OUT_CNT * 20,
                         OUT_CNT * 20, OUT_CNT + 6 + 1,
                         freq=int(100e6))

    def test_HlsPythonHwWhile3(self):
        IN_CNT = 32
        in_t = Bits(8)
        dataIn = [in_t.from_py(self._rand.getrandbits(2)) for _ in range(IN_CNT)]
        self._test_OneInOneOut(HlsPythonHwWhile3(), HlsPythonHwWhile3.model,
                               dataIn, wallTimeRtlClks=IN_CNT + 9 + 1)

    def test_HlsPythonHwWhile4(self, uCls=HlsPythonHwWhile4):
        IN_CNT = 32
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(IN_CNT)]
        self._test_OneInOneOut(uCls(), uCls.model, dataIn)

    def test_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(uCls=HlsPythonHwWhile5)

    def test_HlsPythonHwWhile6(self):
        self.test_HlsPythonHwWhile4(uCls=HlsPythonHwWhile6)

    def test_MovingOneGen(self):
        OUT_CNT = 10
        self._testOneOut(MovingOneGen(), MovingOneGen.model, OUT_CNT,
                         OUT_CNT * 20, OUT_CNT * 20,
                         OUT_CNT * 20, OUT_CNT + 1,
                         freq=int(100e6))

    def test_LoopCondBitSet(self):
        IN_CNT = 12
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(IN_CNT)]
        self._test_OneInOneOut(LoopCondBitSet(), LoopCondBitSet.model, dataIn)

    def test_LoopZeroPadCompareShift(self):
        u = LoopZeroPadCompareShift()
        u.DATA_WIDTH = 4
        t = Bits(u.DATA_WIDTH)
        dataIn = [t.from_py(13), t.from_py(3)]
        self._test_OneInOneOut(u, u.model, dataIn,
                                wallTimeIr=64,
                                wallTimeOptIr=64,
                                wallTimeOptMir=6,
                                )

    def test_PragmaInline_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(uCls=PragmaInline_HlsPythonHwWhile5)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    u = LoopZeroPadCompareShift()
    u.DATA_WIDTH = 4
    # u = HlsPythonHwWhile1()
    u.CLK_FREQ = int(1e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE.union(HlsDebugBundle.DBG_FRONTEND))))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([StmWhile_sim_TC("test_LoopZeroPadCompareShift")])
    # suite = testLoader.loadTestsFromTestCase(StmWhile_ll_TC)
    suite = testLoader.loadTestsFromTestCase(StmWhile_sim_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
