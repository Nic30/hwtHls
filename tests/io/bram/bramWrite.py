
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import BramPort_withoutClk
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope


class BramWrite(Unit):
    """
    Sequentially write counter to BRAM port.
    """

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.ADDR_WIDTH = Param(4)
        self.DATA_WIDTH = Param(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._paramsShared():
            self.ram: BramPort_withoutClk = BramPort_withoutClk()._m()
            ram = self.ram
            ram.HAS_W = True
            ram.HAS_R = False

    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        i = Bits(self.ADDR_WIDTH).from_py(0)
        while BIT.from_py(1):
            hls.write(i._reinterpret_cast(self.ram.din._dtype), ram[i]) 
            i += 1

    def _impl(self) -> None:
        hls = HlsScope(self)
        
        ram = BramArrayProxy(hls, self.ram)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = BramWrite()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
