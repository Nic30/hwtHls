#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOBramPort_noClk
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope
from hwtHls.frontend.pyBytecode import hlsBytecode


class BramWrite(HwModule):
    """
    Sequentially write counter to BRAM port.
    """

    def _config(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(4)
        self.DATA_WIDTH = HwParam(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.ram: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()
            ram = self.ram
            ram.HAS_W = True
            ram.HAS_R = False

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        i = HBits(self.ADDR_WIDTH).from_py(0)
        while BIT.from_py(1):
            hls.write(i._reinterpret_cast(self.ram.din._dtype), ram[i])
            i += 1

    def _impl(self) -> None:
        hls = HlsScope(self)

        ram = BramArrayProxy(hls, self.ram)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = BramWrite()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
