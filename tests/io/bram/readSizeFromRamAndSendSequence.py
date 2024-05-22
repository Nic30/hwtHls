#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIOBramPort_noClk, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope
from tests.frontend.pyBytecode.stmWhile import TRUE
from hwt.pyUtils.typingFuture import override


class ReadSizeFromRamAndSendSequence(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(16)
        self.DATA_WIDTH = HwParam(16)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        self.index = HwIODataRdVld()
        self.index.DATA_WIDTH = self.ADDR_WIDTH
        with self._hwParamsShared():
            self.ram = HwIOBramPort_noClk()._m()
            self.ram.HAS_W = False
            self.out = HwIODataRdVld()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        """
        Read index to ram and send sequence of size stored at ram[index] (size-1 to 0)
        """
        while TRUE:
            index = hls.read(self.index).data
            i = hls.read(ram[index]).data
            while TRUE:
                hls.write(i, self.out)
                if i._eq(0):
                    break
                i -= 1

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, BramArrayProxy(hls, self.ram))
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle

    m = ReadSizeFromRamAndSendSequence()
    m.CLK_FREQ = int(50e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

