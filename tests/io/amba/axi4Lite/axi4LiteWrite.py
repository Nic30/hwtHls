
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Lite import Axi4LiteArrayProxy
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4Lite import Axi4Lite
from pyMathBitPrecise.bit_utils import mask


class Axi4LiteWrite(Unit):
    """
    Sequentially write counter to BRAM port.
    """

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.ADDR_WIDTH = Param(4 + 3)
        self.DATA_WIDTH = Param(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._paramsShared():
            self.ram: Axi4Lite = Axi4Lite()._m()
            self.ram.HAS_R = False

    def mainThread(self, hls: HlsScope, ram: Axi4LiteArrayProxy):
        i = Bits(self.ADDR_WIDTH).from_py(0)
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
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    u = Axi4LiteWrite()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
