#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axi4s import axi4s_send_bytes
from hwtSimApi.utils import freq_to_period
from tests.io.amba.axi4Stream.axi4sPacketCntr import Axi4SPacketCntr


class Axi4SPacketCntrTC(SimTestCase):

    def _test_pkt_cnt(self, DATA_WIDTH:int, cls=Axi4SPacketCntr, LENS=[1, 2, 3], f=int(1e6)):
        dut = cls()
        dut.CLK_FREQ = f
        dut.DATA_WIDTH = DATA_WIDTH
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        
        for LEN in LENS:
            axi4s_send_bytes(dut.i, list(range(LEN)))

        t = int(freq_to_period(dut.clk.FREQ)) * (len(dut.i._ag.data) + 10) 
        self.runSim(t)
        self.assertValEqual(dut.pkt_cnt._ag.data[-1], len(LENS))

    def test_Axi4SPacketCntr_8b(self):
        self._test_pkt_cnt(8)

    def test_Axi4SPacketCntr_16b(self):
        self._test_pkt_cnt(16)

    def test_Axi4SPacketCntr_24b(self):
        self._test_pkt_cnt(24)

    def test_Axi4SPacketCntr_48b(self):
        self._test_pkt_cnt(48)


if __name__ == '__main__':
    import unittest
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # m = Axi4SPacketCntr()
    # m.CLK_FREQ = int(1e6)
    # m.DATA_WIDTH = 16
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
    
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SPacketCntrTC("test_Axi4SPacketCntr_16b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SPacketCntrTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
