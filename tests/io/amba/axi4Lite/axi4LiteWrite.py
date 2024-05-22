#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Lite import Axi4LiteArrayProxy
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4Lite import Axi4Lite
from pyMathBitPrecise.bit_utils import mask


class Axi4LiteWrite(HwModule):
    """
    Sequentially write counter to BRAM port.
    """

    def _config(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(4 + 3)
        self.DATA_WIDTH = HwParam(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.ram: Axi4Lite = Axi4Lite()._m()
            self.ram.HAS_R = False

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: Axi4LiteArrayProxy):
        i = HBits(self.ADDR_WIDTH).from_py(0)
        while BIT.from_py(1):
            w = ram.wWordT.from_py(None)
            w.data = i._reinterpret_cast(ram.dataWordT)
            w.strb = mask(w.strb._dtype.bit_length())
            hls.write(w, ram[i])
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
    m = Axi4LiteWrite()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
