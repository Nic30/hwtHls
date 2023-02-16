#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axis import axis_send_bytes
from hwtSimApi.utils import freq_to_period
from tests.io.amba.axiStream.axisPacketByteCntr import AxiSPacketByteCntr0, AxiSPacketByteCntr1, \
    AxiSPacketByteCntr2, AxiSPacketByteCntr3


class AxiSPacketCntrTC(SimTestCase):

    def _test_byte_cnt(self, DATA_WIDTH:int, cls=AxiSPacketByteCntr0, LENS=[1, 2, 3, 4], T_MUL=1, CLK_FREQ=int(1e6)):
        u = cls()
        u.DATA_WIDTH = DATA_WIDTH
        u.CLK_FREQ = CLK_FREQ
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        
        for LEN in LENS:
            axis_send_bytes(u.i, list(range(LEN)))

        t = int(freq_to_period(u.CLK_FREQ)) * (len(u.i._ag.data) + 10) * T_MUL
        self.runSim(t)
        self.assertValEqual(u.byte_cnt._ag.data[-1], sum(LENS))
     
    def test_AxiSPacketByteCntr0_8b(self):
        self._test_byte_cnt(8)

    def test_AxiSPacketByteCntr0_16b(self):
        self._test_byte_cnt(16)

    def test_AxiSPacketByteCntr0_24b(self):
        self._test_byte_cnt(24)

    def test_AxiSPacketByteCntr0_48b(self):
        self._test_byte_cnt(48)

    def test_AxiSPacketByteCntr1_8b(self):
        self._test_byte_cnt(8, cls=AxiSPacketByteCntr1)

    def test_AxiSPacketByteCntr1_16b(self):
        self._test_byte_cnt(16, cls=AxiSPacketByteCntr1)

    def test_AxiSPacketByteCntr1_24b(self):
        self._test_byte_cnt(24, cls=AxiSPacketByteCntr1)

    def test_AxiSPacketByteCntr1_48b(self):
        self._test_byte_cnt(48, cls=AxiSPacketByteCntr1)

    #def test_AxiSPacketByteCntr2_8b(self):
    #    self._test_byte_cnt(8, cls=AxiSPacketByteCntr2)
    #
    #def test_AxiSPacketByteCntr2_16b(self):
    #    self._test_byte_cnt(16, cls=AxiSPacketByteCntr2)
    #
    #def test_AxiSPacketByteCntr2_24b(self):
    #    self._test_byte_cnt(24, cls=AxiSPacketByteCntr2)
    #
    #def test_AxiSPacketByteCntr2_48b(self):
    #    self._test_byte_cnt(48, cls=AxiSPacketByteCntr2)
    #
    #def test_AxiSPacketByteCntr3_8b(self):
    #    self._test_byte_cnt(8, cls=AxiSPacketByteCntr3)
    #
    #def test_AxiSPacketByteCntr3_16b(self):
    #    self._test_byte_cnt(16, cls=AxiSPacketByteCntr3)
    #
    #def test_AxiSPacketByteCntr3_24b(self):
    #    self._test_byte_cnt(24, cls=AxiSPacketByteCntr3)
    #
    #def test_AxiSPacketByteCntr3_48b(self):
    #    self._test_byte_cnt(48, cls=AxiSPacketByteCntr3)


if __name__ == '__main__':
    import unittest
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # u = AxiSPacketByteCntr0()
    # u.CLK_FREQ = int(1e6)
    # u.DATA_WIDTH = 8
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
    
    suite = unittest.TestSuite()
    # suite.addTest(AxiSPacketCntrTC('test_AxiSPacketByteCntr1_16b'))
    suite.addTest(unittest.makeSuite(AxiSPacketCntrTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
