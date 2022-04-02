#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.statementsIo import IN_STREAM_POS
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.thread import HlsStreamProcPyThread
from hwtHls.ssa.translation.fromPython.markers import PythonBytecodeInPreproc
from hwtLib.amba.axis import AxiStream
from hwtLib.types.ctypes import uint16_t, uint8_t
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE
from hwtLib.types.net.ip import IPv4Header_t, IP_PROTOCOL, ipv4_t
from hwtLib.types.net.udp import UDP_header_t


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
    
    def parseEth(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            eth = PythonBytecodeInPreproc(hls.read(self.i, Eth2Header_t, inStreamPos=IN_STREAM_POS.BEGIN))
            if eth.type._eq(ETHER_TYPE.IPv4):
                ipv4 = PythonBytecodeInPreproc(hls.read(self.i, IPv4Header_t))
                if ipv4.protocol._eq(IP_PROTOCOL.UDP):
                    udp = PythonBytecodeInPreproc(hls.read(self.i, UDP_header_t))
                    hls.write(ipv4.src, self.src_ip)
                    hls.write(udp.srcp, self.srcp)
            hls.read(self.i, uint8_t, inStreamPos=IN_STREAM_POS.END)

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        hls.thread(HlsStreamProcPyThread(hls, self.parseEth, hls))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform, makeDebugPasses
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSParseUdpIpv4()
    u.CLK_FREQ = int(130e6)
    p = VirtualHlsPlatform(**makeDebugPasses("tmp"))
    print(to_rtl_str(u, target_platform=p))
