#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.math import log2ceil
from hwtHls.frontend.pragmaLoop import PyBytecodeLLVMLoopUnroll
from pyMathBitPrecise.bit_utils import mask
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.bitOpt.shifter import ShifterLeft0, ShifterLeft1, \
    ShifterLeftBarrelUsingLoop0, ShifterLeftBarrelUsingLoop1, ShifterLeftBarrelUsingLoop2, \
    ShifterLeftBarrelUsingPyExprConstructor, ShifterLeftUsingHwLoopWithWhileNot0, \
    ShifterLeftUsingHwLoopWithBreakIf0
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule


class ShifterTC(BaseIrMirRtl_TC):

    def _test_shifter(self, dut: ShifterLeft0, freq=int(1e6), timeMultiplier=1):
        dut.CLK_FREQ = freq
        MASK = mask(dut.DATA_WIDTH)
        TEST_DATA = [
            (MASK, i) for i in range(dut.DATA_WIDTH)
        ]
        REF_DATA = [MASK & (d << sh) for d, sh in TEST_DATA]

        dataTy = HBits(dut.DATA_WIDTH)
        shTy = HBits(log2ceil(dut.DATA_WIDTH))
        TEST_DATA_data = tuple(dataTy.from_py(d) for d, _ in TEST_DATA)
        TEST_DATA_sh = tuple(shTy.from_py(sh) for _, sh in TEST_DATA)

        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        wallTime = len(REF_DATA) * 1000
        passTests.setTimeLimits(wallTimeIr=wallTime, wallTimeMir=wallTime, wallTimeRtl=(len(REF_DATA) + 1) * timeMultiplier)
        passTests.bindDataByInOut((TEST_DATA_data, TEST_DATA_sh), (REF_DATA,), PORT_NAMES=("i_data", "i_sh", "o"))
        passTests.test_allInOne()
        self.rtl_simulator_cls = None

    def test_ShifterLeft0(self):
        dut = ShifterLeft0()
        self._test_shifter(dut)

    def test_ShifterLeft1(self):
        dut = ShifterLeft1()
        self._test_shifter(dut,
                           # runTestAfterEachPass=True
                           )

    def test_ShifterLeftUsingHwLoopWithWhileNot0_noUnroll(self):
        dut = ShifterLeftUsingHwLoopWithWhileNot0()
        dut.DATA_WIDTH = 3
        self._test_shifter(dut, timeMultiplier=8,  # debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                                                  #   HlsDebugBundle.DBG_4_0_addSignalNamesToData})
        )

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrol2(self):
        dut = ShifterLeftUsingHwLoopWithWhileNot0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 2)
        self._test_shifter(dut, timeMultiplier=4,
                          # debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
                          #     HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                          #     HlsDebugBundle.DBG_4_0_addSignalNamesToData})
        )

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrol4(self):
        dut = ShifterLeftUsingHwLoopWithWhileNot0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 4)
        self._test_shifter(dut, timeMultiplier=2)

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrolFull(self):
        dut = ShifterLeftUsingHwLoopWithWhileNot0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, dut.DATA_WIDTH - 1)
        self._test_shifter(dut)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_noUnroll(self):
        dut = ShifterLeftUsingHwLoopWithBreakIf0()
        # dut.DATA_WIDTH = 3
        # dut.FN_META = PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass", ])
        # , debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_20_addSignalNamesToSync})
        self._test_shifter(dut, timeMultiplier=8)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrol2(self):
        dut = ShifterLeftUsingHwLoopWithBreakIf0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 2)
        self._test_shifter(dut, timeMultiplier=4,
                           # debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
                           #    HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                           #    HlsDebugBundle.DBG_4_0_addSignalNamesToData}),
                           # runTestAfterEachPass=True,
                           )

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrol4(self):
        dut = ShifterLeftUsingHwLoopWithBreakIf0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 4)
        self._test_shifter(dut, timeMultiplier=2)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrolFull(self):
        dut = ShifterLeftUsingHwLoopWithBreakIf0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, dut.DATA_WIDTH - 1)
        self._test_shifter(dut, timeMultiplier=1.2  # ,
            # llvmCliArgs=[
            # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            # LLVM_CLI_COMMON_OPTS.VERIFY_EACH, ],
            # runTestAfterEachPass=True,
        )

    def test_ShifterLeftBarrelUsingLoop0(self):
        dut = ShifterLeftBarrelUsingLoop0()
        self._test_shifter(dut)

    def test_ShifterLeftBarrelUsingLoop1(self):
        dut = ShifterLeftBarrelUsingLoop1()
        self._test_shifter(dut)

    def test_ShifterLeftBarrelUsingLoop2(self):
        dut = ShifterLeftBarrelUsingLoop2()
        self._test_shifter(dut)

    def test_ShifterLeftBarrelUsingPyExprConstructor(self):
        dut = ShifterLeftBarrelUsingPyExprConstructor()
        self._test_shifter(dut)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.virtual import VirtualHlsPlatform
    dut = ShifterLeft0()
    # dut.DATA_WIDTH = 3
    # # u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, dut.DATA_WIDTH - 1)
    dut.CLK_FREQ = int(1e6)
    # print(to_rtl_str(dut, target_platform=VirtualHlsPlatform(
    #     # debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
    #     #     HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
    #     #     HlsDebugBundle.DBG_4_0_addSignalNamesToData,
    #     # }),
    #     llvmCliArgs=[LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
    #                  # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
    #                   ]
    # )))

    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(ShifterTC)
    # suite = unittest.TestSuite([ShifterTC("test_ShifterLeftUsingHwLoopWithBreakIf0_unrol2")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

