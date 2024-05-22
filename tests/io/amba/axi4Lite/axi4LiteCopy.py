#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Lite import Axi4LiteArrayProxy
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4Lite import Axi4Lite
from pyMathBitPrecise.bit_utils import mask
from tests.io.bram.bramRead import BramRead


class Axi4LiteCopy(BramRead):
    """
    Sequentially read data from Axi4Lite port and write it using same interface with address after beginning at specified OFFSET.
    """

    def _config(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(5 + 3)
        self.OFFSET = HwParam(16)  # specified in bus words
        self.SIZE = HwParam(8)  # specified in bus words
        self.DATA_WIDTH = HwParam(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.ram: Axi4Lite = Axi4Lite()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: Axi4LiteArrayProxy):
        i = ram.indexT.from_py(0)
        while BIT.from_py(1):
            d = hls.read(ram[i]).data.data
            w = ram.wWordT.from_py(None)
            w.data = d
            w.strb = mask(w.strb._dtype.bit_length())
            hls.write(w, ram[i + self.OFFSET // (self.DATA_WIDTH // 8)])
            if i._eq(self.SIZE - 1):
                i = 0
            else:
                i += 1

    def _impl(self) -> None:
        hls = HlsScope(self)
        ram = Axi4LiteArrayProxy(hls, self.ram)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4LiteCopy()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
