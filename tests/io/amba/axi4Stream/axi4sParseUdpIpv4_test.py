#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
import unittest

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE
from hwtLib.types.net.ip import IPv4Header_t, IP_PROTOCOL, IPv4, IHL_DEFAULT
from hwtLib.types.net.udp import UDP_header_t
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import  int_to_int_list
from tests.io.amba.axi4Stream.axi4sParserUdpIpv4 import Axi4SParseUdpIpv4


class Axi4SParseUdpIpv4TC(SimTestCase):

    def _test_parse(self, DATA_WIDTH: int):
        dut = Axi4SParseUdpIpv4()
        dut.DATA_WIDTH = DATA_WIDTH
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        # Test cases: different source IPs and source UDP ports for IPv4+UDP packets
        testCases = [
            (
                0x0a000001,  # 10.0.0.1
                1234,
            ),
            (
                 0x0a000002,  # 10.0.0.2
                 5678,
            ),
            (
                 0x64000101,  # 100.0.1.1
                 8080,
            ),
        ]

        expected_ips = []
        expected_ports = []
        pkt_t = HStruct(
            (Eth2Header_t, "eth"),
            (IPv4Header_t, "ip"),
            (UDP_header_t, "udp"),
        )
        fu = Axi4StreamSimFrameUtils.from_HwIO(dut.i)
        for srcIp, srcPort in testCases:
            # Create Ethernet header (IPv4 type)
            pkt = pkt_t.from_py({
                "eth": {
                    "type": ETHER_TYPE.IPv4,
                },
                "ip": {
                    "ihl": IHL_DEFAULT,
                    "version": IPv4,
                    "protocol": IP_PROTOCOL.UDP,
                    "src": srcIp,
                },
                "udp": {
                    "srcp": srcPort,
                }
            })

            # Pack headers into single frame
            full_frame = pkt._reinterpret_cast(HBits(pkt_t.bit_length()))
            full_frame_int = full_frame.val & full_frame.vld_mask

            # Convert to byte list for AXI4-Stream
            data = int_to_int_list(full_frame_int, 8,
                                   ceil(pkt_t.bit_length() / 8))

            fu.send_bytes(data, dut.i._ag.data)

            expected_ips.append(srcIp)
            expected_ports.append(srcPort)

        CLK_PERIOD = int(freq_to_period(dut.CLK_FREQ))
        t = CLK_PERIOD * (len(dut.i._ag.data) * len(testCases) + 20)
        self.runSim(t)

        self.assertValSequenceEqual(
            [int(x) for x in dut.src_ip._ag.data],
            expected_ips,
            "[%s] != [%s]" % (
                ", ".join("0x%x" % int(x) for x in dut.src_ip._ag.data),
                ", ".join("0x%x" % x for x in expected_ips)
            )
        )

        self.assertValSequenceEqual(
            [int(x) for x in dut.srcp._ag.data],
            expected_ports,
            "[%s] != [%s]" % (
                ", ".join("0x%x" % int(x) for x in dut.srcp._ag.data),
                ", ".join("0x%x" % x for x in expected_ports)
            )
        )

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
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle
    #
    # m = Axi4SParseUdpIpv4()
    # m.DATA_WIDTH = 8
    # p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    # print(to_rtl_str(m, target_platform=p))

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4SParseUdpIpv4TC)
    # suite = unittest.TestSuite([Axi4SParseUdpIpv4TC("test_parse_512b")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
