#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.amba.axi4SSegmentedSimFrameUtils import Axi4StreamSegmentedFrameUtils
from tests.io.amba.axi4Stream.axi4sPacketByteCntr_test import _Axi4SPacketByteCntrTC
from tests.io.amba.axi4StreamSegmented.axi4ssPacketByteCntr import Axi4SSPacketByteCntr_readByte, \
    Axi4SSPacketByteCntr_readBusWord, Axi4SSPacketByteCntr_readSegmentWord
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS, HlsDebugBundle


class Axi4SSPacketByteCntrTC(_Axi4SPacketByteCntrTC):
    _Axi4StreamSimFrameUtils = Axi4StreamSegmentedFrameUtils

    def _test_byte_cnt(self, DATA_WIDTH:int, SEGMENT_CNT:int=1, cls=Axi4SSPacketByteCntr_readByte,
                       LENS=[1, 2, 3, 4], T_MUL=1, CLK_FREQ=int(1e6),
                       SUM_ONLY:bool=True, TEST_IR:bool=True, TEST_MIR:bool=False, platformKwargs=dict(
                           # debugFilter={ *HlsDebugBundle.ALL_RELIABLE,
                           #              # HlsDebugBundle.DBG_20_addSignalNamesToSync,
                           #              # HlsDebugBundle.DBG_20_addSignalNamesToData,
                           #              },
                           llvmCliArgs=[LLVM_CLI_COMMON_OPTS.VERIFY_EACH, ],
                           # runTestAfterEachPass=True
                           )):
        dut = cls()
        dut.SEGMENT_CNT = SEGMENT_CNT
        dut.SEGMENT_DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = CLK_FREQ
        self._run_test_byte_cnt(dut, LENS, T_MUL, CLK_FREQ, SUM_ONLY, TEST_IR, TEST_MIR, platformKwargs=platformKwargs)

    def test_Axi4SSPacketByteCntr_readByte_1x8b(self):
        self._test_byte_cnt(8, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_1x16b(self):
        self._test_byte_cnt(16, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_1x24b(self):
        self._test_byte_cnt(24, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_1x48b(self):
        self._test_byte_cnt(48, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_2x8b(self):
        self._test_byte_cnt(8, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_2x16b(self):
        self._test_byte_cnt(16, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_2x24b(self):
        self._test_byte_cnt(24, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_2x48b(self):
        self._test_byte_cnt(48, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_3x8b(self):
        self._test_byte_cnt(8, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_3x16b(self):
        self._test_byte_cnt(16, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_3x24b(self):
        self._test_byte_cnt(24, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_3x48b(self):
        self._test_byte_cnt(48, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readByte)

    #####################################################################
    def test_Axi4SSPacketByteCntr_readBusWord_1x8b(self):
        self._test_byte_cnt(8, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_1x16b(self):
        self._test_byte_cnt(16, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_1x24b(self):
        self._test_byte_cnt(24, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_1x48b(self):
        self._test_byte_cnt(48, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_2x8b(self):
        self._test_byte_cnt(8, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_2x16b(self):
        self._test_byte_cnt(16, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_2x24b(self):
        self._test_byte_cnt(24, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_2x48b(self):
        self._test_byte_cnt(48, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_3x8b(self):
        self._test_byte_cnt(8, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_3x16b(self):
        self._test_byte_cnt(16, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_3x24b(self):
        self._test_byte_cnt(24, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readBusWord)

    def test_Axi4SSPacketByteCntr_readBusWord_3x48b(self):
        self._test_byte_cnt(48, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readBusWord)

    #####################################################################
    def test_Axi4SSPacketByteCntr_readSegmentWord_1x8b(self):
        self._test_byte_cnt(8, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_1x16b(self):
        self._test_byte_cnt(16, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_1x24b(self):
        self._test_byte_cnt(24, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_1x48b(self):
        self._test_byte_cnt(48, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_2x8b(self):
        self._test_byte_cnt(8, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_2x16b(self):
        self._test_byte_cnt(16, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_2x24b(self):
        self._test_byte_cnt(24, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_2x48b(self):
        self._test_byte_cnt(48, SEGMENT_CNT=2, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_3x8b(self):
        self._test_byte_cnt(8, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_3x16b(self):
        self._test_byte_cnt(16, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_3x24b(self):
        self._test_byte_cnt(24, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readSegmentWord)

    def test_Axi4SSPacketByteCntr_readSegmentWord_3x48b(self):
        self._test_byte_cnt(48, SEGMENT_CNT=3, cls=Axi4SSPacketByteCntr_readSegmentWord)


if __name__ == '__main__':
    import unittest
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    # m = Axi4SSPacketByteCntr_readWord()
    # m.CLK_FREQ = int(1e6)
    # m.SEGMENT_CNT = 1
    # m.SEGMENT_DATA_WIDTH = 16
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4SSPacketByteCntrTC)
    # suite = unittest.TestSuite([Axi4SSPacketByteCntrTC("test_Axi4SSPacketByteCntr_readSegmentWord_3x8b")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
