#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.amba.axi4SSegmented import Axi4StreamSegmentedFrameUtils
from tests.io.amba.axi4Stream.axi4sPacketByteCntr_test import _Axi4SPacketByteCntrTC
from tests.io.amba.axi4StreamSegmented.axi4ssPacketByteCntr import Axi4SSPacketByteCntr_readByte, \
    Axi4SSPacketByteCntr_readWord


class Axi4SSPacketCntrTC(_Axi4SPacketByteCntrTC):
    _Axi4StreamFrameUtils = Axi4StreamSegmentedFrameUtils

    def _test_byte_cnt(self, DATA_WIDTH:int, SEGMENT_CNT:int=1, cls=Axi4SSPacketByteCntr_readByte, LENS=[1, 2, 3, 4], T_MUL=1, CLK_FREQ=int(1e6),
                       SUM_ONLY:bool=True, TEST_IR:bool=False, TEST_MIR:bool=False):
        dut = cls()
        dut.SEGMENT_CNT = SEGMENT_CNT
        dut.SEGMENT_DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = CLK_FREQ
        self._run_test_byte_cnt(dut, LENS, T_MUL, CLK_FREQ, SUM_ONLY, TEST_IR, TEST_MIR)

    def test_Axi4SSPacketByteCntr_readByte_1x8b(self):
        self._test_byte_cnt(8, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_1x16b(self):
        self._test_byte_cnt(16, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_1x24b(self):
        self._test_byte_cnt(24, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readByte_1x48b(self):
        self._test_byte_cnt(48, cls=Axi4SSPacketByteCntr_readByte)

    def test_Axi4SSPacketByteCntr_readWord_1x8b(self):
        self._test_byte_cnt(8, cls=Axi4SSPacketByteCntr_readWord)

    def test_Axi4SSPacketByteCntr_readWord_1x16b(self):
        self._test_byte_cnt(16, cls=Axi4SSPacketByteCntr_readWord)

    def test_Axi4SSPacketByteCntr_readWord_1x24b(self):
        self._test_byte_cnt(24, cls=Axi4SSPacketByteCntr_readWord)

    def test_Axi4SSPacketByteCntr_readWord_1x48b(self):
        self._test_byte_cnt(48, cls=Axi4SSPacketByteCntr_readWord)


if __name__ == '__main__':
    import unittest
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    # m = Axi4SPacketByteCntr3()
    # m.CLK_FREQ = int(1e6)
    # m.DATA_WIDTH = 16
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SPacketCntrTC("test_Axi4SPacketByteCntr2_16b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SSPacketCntrTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
