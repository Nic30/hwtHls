#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.ctypes import uint16_t
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE
from hwtLib.types.net.ip import IPv4Header_t, IP_PROTOCOL, ipv4_t
from hwtLib.types.net.udp import UDP_header_t


class Axi4SParseUdpIpv4(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(512)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
            self.src_ip: HwIOStructRdVld[ipv4_t] = HwIOStructRdVld()._m()
            self.src_ip.T = ipv4_t

            self.srcp: HwIOStructRdVld[uint16_t] = HwIOStructRdVld()._m()
            self.srcp.T = HBits(16)

    @hlsBytecode
    def parseEth(self, hls: HlsScope):
        p = PyBytecodeInPreproc
        i = IoProxyAxi4Stream(hls, self.i)
        while BIT.from_py(1):
            i.readStartOfFrame()
            eth = p(i.read(Eth2Header_t))
            if eth.data.type._eq(ETHER_TYPE.IPv4):
                ipv4 = p(i.read(IPv4Header_t))
                if ipv4.data.protocol._eq(IP_PROTOCOL.UDP):
                    udp = p(i.read(UDP_header_t))
                    hls.write(ipv4.data.src, self.src_ip)
                    hls.write(udp.data.srcp, self.srcp)
            i.readEndOfFrame()

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.parseEth, hls))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4SParseUdpIpv4()
    m.CLK_FREQ = int(130e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))
