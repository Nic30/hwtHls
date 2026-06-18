#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional, Literal

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pragmaLoop import PyBytecodeLLVMLoopUnroll, \
    PyBytecodeStreamLoopUnroll
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from tests.io.amba.axi4Stream.axi4sCopyByteByByte import Axi4SPacketCopyByteByByte
from tests.passTestInjectorForStreamHwModule import PassTestInjectorForStreamHwModule


class Axi4SPacketCopyByteByByteTC(SimTestCase):
    StreamFrameUtils = Axi4StreamSimFrameUtils

    def _test(self, DATA_WIDTH:int, OUT_DATA_WIDTH:int, FRAME_LENGTHS:List[int],
        UNROLL:Optional[Literal[PyBytecodeStreamLoopUnroll]]=None, freq=int(1e6),
        rtlSimTimeMultiplier=2.0,
        cls=Axi4SPacketCopyByteByByte):

        dut = cls()
        dut.UNROLL = UNROLL
        dut.CLK_FREQ = freq
        dut.DATA_WIDTH = DATA_WIDTH
        dut.OUT_DATA_WIDTH = OUT_DATA_WIDTH

        refFrames = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFrames.append(data)

        passTests = PassTestInjectorForStreamHwModule(dut, self, self.StreamFrameUtils)
        passTests.setTimeLimits(wallTimeRtlDefaultMultiplier=rtlSimTimeMultiplier)
        passTests.bindDataByInOut((refFrames,), (refFrames,))
        passTests.test_allInOne(
            # platformKwargs=dict(
            #      debugFilter={
            #          *HlsDebugBundle.ALL_RELIABLE,
            #          HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
            #          HlsDebugBundle.DBG_4_0_addSignalNamesToData,
            #       },
            #       llvmCliArgs=[
            #          # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            #          # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
            #          # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
            #       ],
            #      # runTestAfterEachPass=True,
            #      # runTestAfterEachIrPass=True,
            #      # runTestAfterEachMirPass=True,
            # )
            )

    def test_1B(self):
        PKT_CNT = 6
        self._test(8, 8, [self._rand.randint(1, 3) for _ in range(PKT_CNT)])

    def test_2B(self):
        PKT_CNT = 6
        self._test(2 * 8, 2 * 8, [self._rand.randint(1, 4) for _ in range(PKT_CNT)])

    def test_2B_to_1B(self):
        PKT_CNT = 6
        FRAME_LENGTHS = [self._rand.randint(1, 4) for _ in range(PKT_CNT)]
        self._test(2 * 8, 8, FRAME_LENGTHS)

    def test_1B_to_2B(self):
        PKT_CNT = 6
        self._test(8, 2 * 8, [self._rand.randint(1, 4) for _ in range(PKT_CNT)])

    def test_3B(self):
        PKT_CNT = 6
        self._test(3 * 8, 3 * 8, [self._rand.randint(1, 9) for _ in range(PKT_CNT)], rtlSimTimeMultiplier=2.5)

    def test_4B(self):
        PKT_CNT = 6
        self._test(4 * 8, 4 * 8, [self._rand.randint(1, 12) for _ in range(PKT_CNT)], rtlSimTimeMultiplier=3.5)

    def _testUnrollForRx(self, WORD_BYTE_CNT:int, PKT_CNT=6):
        self._test(WORD_BYTE_CNT * 8, WORD_BYTE_CNT * 8, [self._rand.randint(1, WORD_BYTE_CNT * 3) for _ in range(PKT_CNT)], UNROLL=PyBytecodeStreamLoopUnroll)

    def test_1B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForRx(1)

    def test_2B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForRx(2)

    def test_3B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForRx(3)

    def test_4B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForRx(4)

    def test_16B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForRx(16)

    def test_64B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForRx(64)

    # :todo: unroll before stream lowering otherwise code explodes
    def test_2B_unroll2(self):
        PKT_CNT = 6
        self._test(2 * 8, 2 * 8, [self._rand.randint(1, 6) for _ in range(PKT_CNT)],
                   UNROLL=PyBytecodeLLVMLoopUnroll(True, 2),
                   rtlSimTimeMultiplier=3)

    def test_4B_unroll2(self):
        PKT_CNT = 6
        self._test(4 * 8, 4 * 8, [self._rand.randint(1, 12) for _ in range(PKT_CNT)],
                   UNROLL=PyBytecodeLLVMLoopUnroll(True, 2),
                   rtlSimTimeMultiplier=4)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.virtual import VirtualHlsPlatform
    m = Axi4SPacketCopyByteByByte()
    # m.UNROLL = PyBytecodeStreamLoopUnroll  # PyBytecodeLLVMLoopUnroll(True, 2)
    # m.UNROLL = PyBytecodeLLVMLoopUnroll(True, 2)
    m.UNROLL = None
    m.DATA_WIDTH = 4 * 8
    m.OUT_DATA_WIDTH = 4 * 8
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(debugFilter={
      *HlsDebugBundle.ALL_RELIABLE,
      # HlsDebugBundle.DBG_20_addSignalNamesToSync
    },
    llvmCliArgs=[
        # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
        # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
        # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
       ],
    )
    # print(to_rtl_str(m, target_platform=p))

    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4SPacketCopyByteByByteTC)
    # suite = unittest.TestSuite([Axi4SPacketCopyByteByByteTC("test_4B")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
