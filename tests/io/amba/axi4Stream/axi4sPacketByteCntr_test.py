#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axi4s import axi4s_send_bytes
from hwtSimApi.utils import freq_to_period
from tests.io.amba.axi4Stream.axi4sPacketByteCntr import Axi4SPacketByteCntr0, Axi4SPacketByteCntr1, \
    Axi4SPacketByteCntr2, Axi4SPacketByteCntr3


class Axi4SPacketCntrTC(SimTestCase):

    def _test_byte_cnt(self, DATA_WIDTH:int, cls=Axi4SPacketByteCntr0, LENS=[1, 2, 3, 4], T_MUL=1, CLK_FREQ=int(1e6)):
        dut = cls()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = CLK_FREQ
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        
        for LEN in LENS:
            axi4s_send_bytes(dut.i, list(range(LEN)))

        t = int(freq_to_period(dut.CLK_FREQ)) * (len(dut.i._ag.data) + 10) * T_MUL
        self.runSim(t)
        self.assertValEqual(dut.byte_cnt._ag.data[-1], sum(LENS))
     
    def test_Axi4SPacketByteCntr0_8b(self):
        self._test_byte_cnt(8)

    def test_Axi4SPacketByteCntr0_16b(self):
        self._test_byte_cnt(16)

    def test_Axi4SPacketByteCntr0_24b(self):
        self._test_byte_cnt(24)

    def test_Axi4SPacketByteCntr0_48b(self):
        self._test_byte_cnt(48)

    def test_Axi4SPacketByteCntr1_8b(self):
        self._test_byte_cnt(8, cls=Axi4SPacketByteCntr1)

    def test_Axi4SPacketByteCntr1_16b(self):
        self._test_byte_cnt(16, cls=Axi4SPacketByteCntr1)

    def test_Axi4SPacketByteCntr1_24b(self):
        self._test_byte_cnt(24, cls=Axi4SPacketByteCntr1)

    def test_Axi4SPacketByteCntr1_48b(self):
        self._test_byte_cnt(48, cls=Axi4SPacketByteCntr1)

    def test_Axi4SPacketByteCntr2_8b(self):
        self._test_byte_cnt(8, cls=Axi4SPacketByteCntr2)
    
    def test_Axi4SPacketByteCntr2_16b(self):
        self._test_byte_cnt(16, cls=Axi4SPacketByteCntr2)
    
    def test_Axi4SPacketByteCntr2_24b(self):
        self._test_byte_cnt(24, cls=Axi4SPacketByteCntr2)
    
    def test_Axi4SPacketByteCntr2_48b(self):
        self._test_byte_cnt(48, cls=Axi4SPacketByteCntr2)
    
    def test_Axi4SPacketByteCntr3_8b(self):
        self._test_byte_cnt(8, cls=Axi4SPacketByteCntr3)
    
    def test_Axi4SPacketByteCntr3_16b(self):
        self._test_byte_cnt(16, cls=Axi4SPacketByteCntr3)
    
    def test_Axi4SPacketByteCntr3_24b(self):
        self._test_byte_cnt(24, cls=Axi4SPacketByteCntr3)
    
    def test_Axi4SPacketByteCntr3_48b(self):
        self._test_byte_cnt(48, cls=Axi4SPacketByteCntr3)


if __name__ == '__main__':
    import unittest
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # m = Axi4SPacketByteCntr0()
    # m.CLK_FREQ = int(1e6)
    # m.DATA_WIDTH = 8
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
    
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SPacketCntrTC("test_Axi4SPacketByteCntr1_16b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SPacketCntrTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
