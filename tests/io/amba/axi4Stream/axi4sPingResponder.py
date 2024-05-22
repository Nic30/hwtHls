#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.std import HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.markers import PyBytecodePreprocHwCopy
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.examples.builders.pingResponder_test import Axi4SPingResponderTC as HwtLibPingResponderTC
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE
from hwtLib.types.net.icmp import ICMP_echo_header_t, ICMP_TYPE
from hwtLib.types.net.ip import IPv4Header_t, ipv4_t, IP_PROTOCOL
from pyMathBitPrecise.bit_utils import reverse_byte_order


echoFrame_t = HStruct(
    (Eth2Header_t, "eth"),
    (IPv4Header_t, "ip"),
    (ICMP_echo_header_t, "icmp"),
)


# https://github.com/hamsternz/FPGA_Webserver/tree/master/hdl/icmp
class Axi4SPingResponder(HwModule):
    """
    Listen for echo request on rx AXI-stream interface and respond
    with echo response on tx interface

    :note: incoming checksum is not checked
    :attention: you have to ping "ping -s 0 <ip>" because unit ignores
        additional data in packet and linux by defaults adds it

    .. hwt-autodoc::
    """

    def _config(self):
        self.DATA_WIDTH = HwParam(256)
        self.USE_STRB = HwParam(False)
        self.CLK_FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.myIp = HwIOSignal(dtype=ipv4_t)

        with self._hwParamsShared():
            self.rx = Axi4Stream()
            self.tx = Axi4Stream()._m()

    @hlsBytecode
    def icmp_checksum(self, header):
        """
        :return: checksum for icmp header
        """
        # [todo] endianity
        # type, code, checksum = 0
        return reverse_byte_order(
            ~(reverse_byte_order(header.identifier) + 
              reverse_byte_order(header.seqNo))
        )

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        while BIT.from_py(1):
            myIp = hls.read(self.myIp).data
            rx.readStartOfFrame()
            p = PyBytecodeInPreproc(rx.read(echoFrame_t))
            pd = p.data
            rx.readEndOfFrame()
            if pd.eth.type._eq(ETHER_TYPE.IPv4) & \
               reverse_byte_order(pd.ip.dst)._eq(myIp) & \
               pd.ip.protocol._eq(IP_PROTOCOL.ICMP) & \
               pd.icmp.type._eq(ICMP_TYPE.ECHO_REQUEST):
                # set fields for reply
                pd.icmp.type = ICMP_TYPE.ECHO_REPLY
                pd.icmp.code = 0
                pd.icmp.checksum = self.icmp_checksum(pd.icmp)
                copy = PyBytecodePreprocHwCopy
                pd.ip.src, pd.ip.dst = copy(pd.ip.dst), copy(pd.ip.src)
                pd.eth.src, pd.eth.dst = copy(pd.eth.dst), copy(pd.eth.src)

                tx.writeStartOfFrame()
                tx.write(pd)
                tx.writeEndOfFrame()
            # else drop packet if it is not echo request for myIp

    def _impl(self):
        hls = HlsScope(self)
        rx = IoProxyAxi4Stream(hls, self.rx)
        tx = IoProxyAxi4Stream(hls, self.tx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, rx, tx)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SPingResponderTC(SimTestCase):
    DATA_WIDTH = 32

    @classmethod
    def setUpClass(cls):
        dut = cls.dut = Axi4SPingResponder()
        dut.DATA_WIDTH = cls.DATA_WIDTH
        cls.compileSim(dut, target_platform=VirtualHlsPlatform())

    def create_ICMP_echo_frame(self, **kwargs):
        return HwtLibPingResponderTC.create_ICMP_echo_frame(self, **kwargs)
        
    def test_reply1x(self):
        HwtLibPingResponderTC.test_reply1x(self)


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Slow
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = Axi4SPingResponder()
    m.DATA_WIDTH = 256
    m.CLK_FREQ = int(100e6)
    print(to_rtl_str(m, target_platform=Artix7Slow(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SPingResponderTC("test_reply1x")])
    suite = testLoader.loadTestsFromTestCase(Axi4SPingResponderTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
