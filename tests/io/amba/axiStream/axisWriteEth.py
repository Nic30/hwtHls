#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.synthesizer.unit import Unit
from hwtLib.amba.axis import AxiStream
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.scope import HlsScope
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axiStream.proxy import IoProxyAxiStream
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwtLib.types.net.ethernet import eth_mac_t, Eth2Header_t, ETHER_TYPE


class AxiSWriteEth(Unit):
    
    def _config(self):
        self.CLK_FREQ = Param(int(100e6))
        AxiStream._config(self)
        
    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.dataOut = AxiStream()._m()

        self.src = Handshaked()
        self.dst = Handshaked()
        for i in [self.src, self.dst]:
            i.DATA_WIDTH = eth_mac_t.bit_length()

    def mainThread(self, hls: HlsScope, dataOut: IoProxyAxiStream):
        while BIT.from_py(1):
            v = Eth2Header_t.from_py(None)
            v.type = ETHER_TYPE.IPv4
            v.src = hls.read(self.src).data
            v.dst = hls.read(self.dst).data
            dataOut.writeStartOfFrame()
            dataOut.write(v)
            dataOut.writeEndOfFrame()

    def _impl(self) -> None:
        hls = HlsScope(self)
        dataOut = IoProxyAxiStream(hls, self.dataOut)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, dataOut))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSWriteEth()
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
