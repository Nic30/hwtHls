#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.interfaces.std import Signal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.byteOrder import reverseByteOrder
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.markers import PyBytecodePreprocHwCopy
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.axiStream.proxy import IoProxyAxiStream
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from hwtLib.examples.builders.pingResponder_test import PingResponderTC as HwtLibPingResponderTC
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE
from hwtLib.types.net.icmp import ICMP_echo_header_t, ICMP_TYPE
from hwtLib.types.net.ip import IPv4Header_t, ipv4_t

echoFrame_t = HStruct(
    (Eth2Header_t, "eth"),
    (IPv4Header_t, "ip"),
    (ICMP_echo_header_t, "icmp"),
)


# https://github.com/hamsternz/FPGA_Webserver/tree/master/hdl/icmp
class PingResponder(Unit):
    """
    Listen for echo request on rx AXI-stream interface and respond
    with echo response on tx interface

    :note: incoming checksum is not checked
    :attention: you have to ping "ping -s 0 <ip>" because unit ignores
        additional data in packet and linux by defaults adds it

    .. hwt-autodoc::
    """

    def _config(self):
        self.DATA_WIDTH = Param(256)
        self.USE_STRB = Param(False)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.myIp = Signal(dtype=ipv4_t)

        with self._paramsShared():
            self.rx = AxiStream()
            self.tx = AxiStream()._m()

    def icmp_checksum(self, header):
        """
        :return: checksum for icmp header
        """
        # [todo] endianity
        # type, code, checksum = 0
        return reverseByteOrder(
            ~(reverseByteOrder(header.identifier) + 
              reverseByteOrder(header.seqNo))
        )

    def mainThread(self, hls: HlsScope, rx: IoProxyAxiStream, tx: IoProxyAxiStream):
        while BIT.from_py(1):
            myIp = hls.read(self.myIp)
            rx.readStartOfFrame()
            p = PyBytecodeInPreproc(rx.read(echoFrame_t))
            pd = p.data
            rx.readEndOfFrame()
            if pd.eth.type._eq(ETHER_TYPE.IPv4) & reverseByteOrder(pd.ip.dst)._eq(myIp) & pd.icmp.type._eq(ICMP_TYPE.ECHO_REQUEST):
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
        rx = IoProxyAxiStream(hls, self.rx)
        tx = IoProxyAxiStream(hls, self.tx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, rx, tx)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


class PingResponderTC(HwtLibPingResponderTC):

    @classmethod
    def setUpClass(cls):
        u = cls.u = PingResponder()
        u.DATA_WIDTH = cls.DATA_WIDTH
        cls.compileSim(u, target_platform=VirtualHlsPlatform())


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Slow
    u = PingResponder()
    u.DATA_WIDTH = 32
    u.CLK_FREQ = int(100e6)
    print(to_rtl_str(u, target_platform=Artix7Slow(debugDir="tmp")))

    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(PingResponderTC('test_reply1x'))
    suite.addTest(unittest.makeSuite(PingResponderTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
