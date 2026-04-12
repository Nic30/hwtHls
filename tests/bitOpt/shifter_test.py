#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque

from hwt.hdl.types.bits import HBits
from hwt.math import log2ceil
from hwtHls.frontend.pragmaLoop import PyBytecodeLLVMLoopUnroll
from hwtHls.platform.debugBundle import DebugId, LLVM_CLI_COMMON_OPTS  # , LLVM_CLI_COMMON_OPTS
from pyMathBitPrecise.bit_utils import mask
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.bitOpt.shifter import ShifterLeft0, ShifterLeft1, \
    ShifterLeftBarrelUsingLoop0, ShifterLeftBarrelUsingLoop1, ShifterLeftBarrelUsingLoop2, \
    ShifterLeftBarrelUsingPyExprConstructor, ShifterLeftUsingHwLoopWithWhileNot0, \
    ShifterLeftUsingHwLoopWithBreakIf0


class ShifterTC(BaseIrMirRtl_TC):

    def _test(self, dut: ShifterLeft0,
                TEST_DATA: list[tuple[int, int]],
                REF_DATA: list[int],
                freq=int(1e6),
                timeMultiplier=1,
                **kwargs):
        """
        :param model: a function which process all inputs and generate all outputs
        For meaning of params check :meth:`~._testOneOut`
        """
        dataTy = HBits(dut.DATA_WIDTH)
        shTy = HBits(log2ceil(dut.DATA_WIDTH))
        TEST_DATA_i = tuple(dataTy.from_py(d) for d, _ in TEST_DATA)
        TEST_DATA_sh = tuple(shTy.from_py(sh) for _, sh in TEST_DATA)

        def prepareIrAndMirArgs():
            o = []
            return (iter(TEST_DATA_i), o, iter(TEST_DATA_sh))

        def checkIrAndMirArgs(args: tuple[deque]):
            dataOut = args[1]
            dataOut = [int(d) for d in dataOut]
            # print("test:", [f"0x{int(d):x}" for d in o])
            self.assertSequenceEqual(dataOut, REF_DATA)
            # self.assertValSequenceEqual(dataOut, REF_DATA)

        def prepareRtlSimArgs(dut: ShifterLeft0):
            for i, sh in TEST_DATA:
                dut.i._ag.data.append(i)
                dut.sh._ag.data.append(sh)

            # CLK_PERIOD = freq_to_period(dut.clk.FREQ)
            dut.i._ag.presetBeforeClk = True
            dut.sh._ag.presetBeforeClk = True
            dut.o._ag.presetBeforeClk = True
            return None

        def checkRtlSimResults(dut: ShifterLeft0, ref: list):
            # self.runSim((int(len(TEST_DATA) * timeMultiplier + 1)) * int(CLK_PERIOD))
            BaseIrMirRtl_TC._test_no_comb_loops(self)
            self.assertValSequenceEqual(dut.o._ag.data, REF_DATA)
        
        wallTime = len(REF_DATA) * 1000
        BaseIrMirRtl_TC._test(self, dut,
            prepareIrAndMirArgs, checkIrAndMirArgs,
            prepareRtlSimArgs, checkRtlSimResults,
            wallTimeIr=wallTime,
            wallTimeOptIr=wallTime,
            wallTimeOptMir=wallTime,
            wallTimeRtlClks=(len(REF_DATA) + 1) * timeMultiplier,
            freq=freq,
            **kwargs
        )

    def _test_shifter(self, dut: ShifterLeft0, timeMultiplier=1,
                **kwargs):
        MASK = mask(dut.DATA_WIDTH)
        TEST_DATA = [
            (MASK, i) for i in range(dut.DATA_WIDTH)
        ]
        REF_DATA = [MASK & (d << sh) for d, sh in TEST_DATA]

        self._test(dut, TEST_DATA, REF_DATA, timeMultiplier=timeMultiplier, **kwargs)
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

