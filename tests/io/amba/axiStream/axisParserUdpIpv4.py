#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from hwtLib.types.ctypes import uint16_t
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE
from hwtLib.types.net.ip import IPv4Header_t, IP_PROTOCOL, ipv4_t
from hwtLib.types.net.udp import UDP_header_t
from hwtHls.io.amba.axiStream.proxy import IoProxyAxiStream
from hwtHls.frontend.pyBytecode import hlsBytecode


class AxiSParseUdpIpv4(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(512)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
            self.src_ip: HsStructIntf[ipv4_t] = HsStructIntf()._m()
            self.src_ip.T = ipv4_t

            self.srcp: HsStructIntf[uint16_t] = HsStructIntf()._m()
            self.srcp.T = Bits(16)

    @hlsBytecode
    def parseEth(self, hls: HlsScope):
        i = IoProxyAxiStream(hls, self.i)
        while BIT.from_py(1):
            i.readStartOfFrame()
            eth = PyBytecodeInPreproc(i.read(Eth2Header_t))
            if eth.data.type._eq(ETHER_TYPE.IPv4):
                ipv4 = PyBytecodeInPreproc(i.read(IPv4Header_t))
                if ipv4.data.protocol._eq(IP_PROTOCOL.UDP):
                    udp = PyBytecodeInPreproc(i.read(UDP_header_t))
                    hls.write(ipv4.data.src, self.src_ip)
                    hls.write(udp.data.srcp, self.srcp)
            i.readEndOfFrame()

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.parseEth, hls))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = AxiSParseUdpIpv4()
    u.CLK_FREQ = int(130e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(u, target_platform=p))
