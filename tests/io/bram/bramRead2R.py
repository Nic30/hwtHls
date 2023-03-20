#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import BramPort_withoutClk, Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope
from hwtHls.frontend.pyBytecode import hlsBytecode


class BramRead2R(Unit):
    """
    Sequentially read data from 2 BRAM ports hidden by a single proxy.
    """

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.ADDR_WIDTH = Param(4)
        self.DATA_WIDTH = Param(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._paramsShared():
            self.dataOut0 = Handshaked()._m()
            self.dataOut1 = Handshaked()._m()
            self.ram0: BramPort_withoutClk = BramPort_withoutClk()._m()
            self.ram1: BramPort_withoutClk = BramPort_withoutClk()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        i = Bits(self.ADDR_WIDTH).from_py(0)
        while BIT.from_py(1):
            d0 = hls.read(ram[i]).data
            d1 = hls.read(ram[i + 1]).data
            hls.write(d0, self.dataOut0)
            hls.write(d1, self.dataOut1)
            i += 2

    def _impl(self) -> None:
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, (self.ram0, self.ram1))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = BramRead2R()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
