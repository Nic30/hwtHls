#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import BramPort_withoutClk, Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope


class ReadSizeFromRamAndSendSequence(Unit):

    def _config(self):
        self.CLK_FREQ = Param(int(100e6))
        self.ADDR_WIDTH = Param(16)
        self.DATA_WIDTH = Param(16)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        self.index = Handshaked()
        self.index.DATA_WIDTH = self.ADDR_WIDTH
        with self._paramsShared():
            self.ram = BramPort_withoutClk()._m()
            self.ram.HAS_W = False
            self.out = Handshaked()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        """
        Read index to ram and send sequence of size stored at ram[index] (size-1 to 0)
        """
        while BIT.from_py(1):
            index = hls.read(self.index).data
            i = hls.read(ram[index]).data
            while BIT.from_py(1):
                hls.write(i, self.out)
                if i._eq(0):
                    break
                i -= 1

    def _impl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, BramArrayProxy(hls, self.ram))
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = ReadSizeFromRamAndSendSequence()
    u.CLK_FREQ = int(50e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

