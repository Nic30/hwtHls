#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
import unittest

from hwt.hdl.types.bits import HBits
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axi4s import axi4s_send_bytes
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE
from hwtSimApi.constants import CLK_PERIOD
from pyMathBitPrecise.bit_utils import  int_to_int_list
from tests.io.amba.axi4Stream.axi4sParseEth import Axi4SParseEth


class Axi4SParseEthTC(SimTestCase):

    def _test_parse(self, DATA_WIDTH):
        dut = Axi4SParseEth()
        dut.DATA_WIDTH = DATA_WIDTH
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dsts = [0x010203040506, 0x111213141516, 0x212223242526, ]
        for dst in dsts:
            v = Eth2Header_t.from_py({
                "dst": dst,
                "src": 0x778899101112,
                "type": ETHER_TYPE.IPv4,
                
            })
            v = int(v._reinterpret_cast(HBits(v._dtype.bit_length())))
            data = int_to_int_list(v, 8, ceil(Eth2Header_t.bit_length() / 8))
            axi4s_send_bytes(dut.i, data)

        t = CLK_PERIOD * (len(dut.i._ag.data) + 5) 
        self.runSim(t)

        self.assertValSequenceEqual(dut.dst_mac._ag.data, dsts, "[%s] != [%s]" % (
            ", ".join("0x%x" % int(i) for i in dut.dst_mac._ag.data),
            ", ".join("0x%x" % int(i) for i in dsts)
        ))

    def test_parse_8b(self):
        self._test_parse(8)

    def test_parse_16b(self):
        self._test_parse(16)

    def test_parse_24b(self):
        self._test_parse(24)

    def test_parse_48b(self):
        self._test_parse(48)

    def test_parse_512b(self):
        self._test_parse(512)


if __name__ == '__main__':

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SParseEthTC("test_parse_24b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SParseEthTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
