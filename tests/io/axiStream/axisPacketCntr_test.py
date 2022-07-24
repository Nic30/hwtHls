#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axis import axis_send_bytes
from hwtSimApi.utils import freq_to_period
from tests.io.axiStream.axisPacketCntr import AxiSPacketCntr


class AxiSPacketCntrTC(SimTestCase):

    def _test_pkt_cnt(self, DATA_WIDTH:int, cls=AxiSPacketCntr, LENS=[1, 2, 3], f=int(1e6)):
        u = cls()
        u.CLK_FREQ = f
        u.DATA_WIDTH = DATA_WIDTH
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        
        for LEN in LENS:
            axis_send_bytes(u.i, list(range(LEN)))

        t = int(freq_to_period(u.clk.FREQ)) * (len(u.i._ag.data) + 10) 
        self.runSim(t)
        self.assertValEqual(u.pkt_cnt._ag.data[-1], len(LENS))

    def test_AxiSPacketCntr_8b(self):
        self._test_pkt_cnt(8)

    def test_AxiSPacketCntr_16b(self):
        self._test_pkt_cnt(16)

    def test_AxiSPacketCntr_24b(self):
        self._test_pkt_cnt(24)

    def test_AxiSPacketCntr_48b(self):
        self._test_pkt_cnt(48)


if __name__ == '__main__':
    import unittest
    # from hwt.synthesizer.utils import to_rtl_str
    # u = AxiSPacketCntr()
    # u.CLK_FREQ = int(1e6)
    # u.DATA_WIDTH = 8
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
    
    suite = unittest.TestSuite()
    # suite.addTest(AxiSPacketCntrTC('test_AxiSPacketByteCntr1_16b'))
    suite.addTest(unittest.makeSuite(AxiSPacketCntrTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
