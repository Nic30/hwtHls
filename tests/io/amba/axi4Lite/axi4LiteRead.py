#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Lite import Axi4LiteArrayProxy
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4Lite import Axi4Lite
from tests.io.bram.bramRead import BramRead


#  packIntf(intf, masterDirEqTo, exclude)
class Axi4LiteRead(BramRead):
    """
    Sequentially read data from Axi4Lite port.
    """

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.ADDR_WIDTH = Param(4 + 3)
        self.DATA_WIDTH = Param(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._paramsShared():
            self.dataOut = Handshaked()._m()
            self.ram: Axi4Lite = Axi4Lite()._m()
            self.ram.HAS_W = False

    def mainThread(self, hls: HlsScope, ram: Axi4LiteArrayProxy):
        i = ram.indexT.from_py(0)
        while BIT.from_py(1):
            d = hls.read(ram[i]).data.data
            hls.write(d, self.dataOut) 
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
    u = Axi4LiteRead()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
