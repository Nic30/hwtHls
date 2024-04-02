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
    LoopCondBitSet, LoopZeroPadCompareShift, HlsPythonHwWhile5b, \
    PragmaInline_HlsPythonHwWhile4


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
                               dataIn, wallTimeRtlClks=IN_CNT + 9 + 20 + 1)

    def test_HlsPythonHwWhile4(self, uCls=HlsPythonHwWhile4):
        IN_CNT = 32
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(IN_CNT)]
        self._test_OneInOneOut(uCls(), uCls.model, dataIn)

    def test_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(uCls=HlsPythonHwWhile5)

    def test_HlsPythonHwWhile5b(self):
        self.test_HlsPythonHwWhile4(uCls=HlsPythonHwWhile5b)

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
                                wallTimeIr=60,
                                wallTimeOptIr=60,
                                wallTimeOptMir=6,
                                )

    def test_PragmaInline_PragmaInline_HlsPythonHwWhile4(self):
        self.test_HlsPythonHwWhile4(uCls=PragmaInline_HlsPythonHwWhile4)

    def test_PragmaInline_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(uCls=PragmaInline_HlsPythonHwWhile5)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    # [fixme] afterPrefix does not add prefix correctly and generates
    # new blocks without loop prefix for inlined blocks
    # * or returns are handled incorrectly
    # * CFG is missing edges and that is why the block is marked non-generated prematurely

    import unittest

    testLoader = unittest.TestLoader()
    # suite1 = unittest.TestSuite([StmWhile_sim_TC("test_LoopZeroPadCompareShift")])
    suite1 = testLoader.loadTestsFromTestCase(StmWhile_ll_TC)
    suite2 = testLoader.loadTestsFromTestCase(StmWhile_sim_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(unittest.TestSuite([suite1, suite2]))
    # runner.run(suite1)
