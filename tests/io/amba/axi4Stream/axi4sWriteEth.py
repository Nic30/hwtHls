#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.net.ethernet import eth_mac_t, Eth2Header_t, ETHER_TYPE


class Axi4SWriteEth(HwModule):

    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        Axi4Stream.hwConfig(self)

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.dataOut = Axi4Stream()._m()

        self.src = HwIODataRdVld()
        self.dst = HwIODataRdVld()
        for i in [self.src, self.dst]:
            i.DATA_WIDTH = eth_mac_t.bit_length()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, dataOut: IoProxyAxi4Stream):
        while BIT.from_py(1):
            v = Eth2Header_t.from_py(None)
            v.type = ETHER_TYPE.IPv4
            v.src = hls.read(self.src).data
            v.dst = hls.read(self.dst).data
            dataOut.writeStartOfFrame()
            dataOut.write(v)
            dataOut.writeEndOfFrame()

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        dataOut = IoProxyAxi4Stream(hls, self.dataOut)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, dataOut))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4SWriteEth()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL)
    print(to_rtl_str(m, target_platform=p))
