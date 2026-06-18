#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwtHls.platform.debugBundle import HlsDebugBundle
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.stmWhile import HlsPythonHwWhile0a, \
    HlsPythonHwWhile1, HlsPythonHwWhile2, HlsPythonHwWhile3, HlsPythonHwWhile4, \
    HlsPythonHwWhile5, HlsPythonHwWhile0b, HlsPythonHwWhile0c, \
    PragmaInline_HlsPythonHwWhile5, HlsPythonHwWhile6, MovingOneGen, \
    LoopCondBitSet, LoopZeroPadCompareShift, HlsPythonHwWhile5b, \
    PragmaInline_HlsPythonHwWhile4, PragmaInline_HlsPythonHwWhile5c
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule


class StmWhile_ll_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsPythonHwWhile0a_ll(self):
        self._test_ll(HlsPythonHwWhile0a)

    def test_HlsPythonHwWhile1_ll(self):
        self._test_ll(HlsPythonHwWhile1)

    def test_HlsPythonHwWhile2_ll(self):
        self._test_ll(HlsPythonHwWhile2)


class StmWhile_sim_TC(BaseIrMirRtl_TC):

    def test_HlsPythonHwWhile0a(self, hwModuleCls:type[HlsPythonHwWhile0a]=HlsPythonHwWhile0a, OUT_CNT=16):
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(OUT_CNT)]

        passTests = PassTestInjectorForDInDOutHwModule(hwModuleCls(), self)
        passTests.setTimeLimits(wallTimeIr=OUT_CNT * 20,
                                wallTimeMir=OUT_CNT * 20,
                                wallTimeRtl=OUT_CNT + 2)
        passTests.test_allInOne_withModel((dataIn,))

    def test_HlsPythonHwWhile0b(self, hwModuleCls:type[HlsPythonHwWhile0b]=HlsPythonHwWhile0b, OUT_CNT=8):
        passTests = PassTestInjectorForDInDOutHwModule(hwModuleCls(), self)
        passTests.setTimeLimits(wallTimeIr=OUT_CNT * 10,
                                wallTimeMir=OUT_CNT * 10,
                                wallTimeRtl=OUT_CNT + 1)
        passTests.test_allInOne_withModel((), OUT_ITEM_CNT_LIMITS=(OUT_CNT,))

    def test_HlsPythonHwWhile0c(self):
        self.test_HlsPythonHwWhile0a(hwModuleCls=HlsPythonHwWhile0c)

    def test_HlsPythonHwWhile1(self):
        self.test_HlsPythonHwWhile0a(HlsPythonHwWhile1)

    def test_HlsPythonHwWhile2(self):
        OUT_CNT = 16
        dut = HlsPythonHwWhile2()
        dut.CLK_FREQ = int(100e6)
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setTimeLimits(wallTimeIr=OUT_CNT * 25,
                                wallTimeMir=OUT_CNT * 20,
                                wallTimeRtl=OUT_CNT + 6 + 1)
        passTests.test_allInOne_withModel((), OUT_ITEM_CNT_LIMITS=(OUT_CNT,))

    def test_HlsPythonHwWhile3(self):
        IN_CNT = 32
        in_t = HBits(8)
        dataIn = [in_t.from_py(self._rand.getrandbits(2)) for _ in range(IN_CNT)]

        passTests = PassTestInjectorForDInDOutHwModule(HlsPythonHwWhile3(), self)
        passTests.setTimeLimits(wallTimeRtl=IN_CNT + 9 + 20 + 1)
        passTests.test_allInOne_withModel((dataIn,))

    def test_HlsPythonHwWhile4(self, mCls=HlsPythonHwWhile4):
        IN_CNT = 32
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(IN_CNT)]
        passTests = PassTestInjectorForDInDOutHwModule(mCls(), self)
        passTests.test_allInOne_withModel((dataIn,))

    def test_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(mCls=HlsPythonHwWhile5)

    def test_HlsPythonHwWhile5b(self):
        self.test_HlsPythonHwWhile4(mCls=HlsPythonHwWhile5b)

    def test_HlsPythonHwWhile6(self):
        self.test_HlsPythonHwWhile4(mCls=HlsPythonHwWhile6)

    def test_MovingOneGen(self):
        OUT_CNT = 10
        dut = MovingOneGen()
        dut.CLK_FREQ = int(100e6)
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setTimeLimits(wallTimeIr=OUT_CNT * 20, wallTimeMir=OUT_CNT * 20, wallTimeRtl=OUT_CNT + 1)
        passTests.test_allInOne_withModel((), OUT_ITEM_CNT_LIMITS=(OUT_CNT,))

    def test_LoopCondBitSet(self):
        IN_CNT = 12
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(IN_CNT)]
        passTests = PassTestInjectorForDInDOutHwModule(LoopCondBitSet(), self)
        passTests.test_allInOne_withModel((dataIn,))

    def test_LoopZeroPadCompareShift(self):
        dut = LoopZeroPadCompareShift()
        dut.DATA_WIDTH = 4
        dut.CLK_FREQ = int(1e6)
        t = HBits(dut.DATA_WIDTH)
        dataIn = [t.from_py(13), t.from_py(3)]
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setTimeLimits(wallTimeIr=100, wallTimeMir=70, wallTimeRtl=6 + 2)
        passTests.test_allInOne_withModel((dataIn,), OUT_ITEM_CNT_LIMITS=(5,))

    def test_PragmaInline_PragmaInline_HlsPythonHwWhile4(self):
        self.test_HlsPythonHwWhile4(mCls=PragmaInline_HlsPythonHwWhile4)

    def test_PragmaInline_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(mCls=PragmaInline_HlsPythonHwWhile5)

    @unittest.expectedFailure
    def test_PragmaInline_HlsPythonHwWhile5c(self):
        self.test_HlsPythonHwWhile4(mCls=PragmaInline_HlsPythonHwWhile5c)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    m = HlsPythonHwWhile3()
    m.CLK_FREQ = int(1e6)
    # m.DATA_WIDTH = 4
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter={
    #     *HlsDebugBundle.ALL_RELIABLE,
    #     HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
    #     HlsDebugBundle.DBG_4_0_addSignalNamesToData,
    # },
    # #    llvmCliArgs=[("print-after-all", 0, "", "true")]
    # )))

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(TC) for TC in
                        (
                            StmWhile_ll_TC,
                            StmWhile_sim_TC
                         )])
    # suite = unittest.TestSuite([StmWhile_sim_TC("test_HlsPythonHwWhile0a")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
