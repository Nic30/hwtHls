#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import BramPort_withoutClk, Handshaked
from hwt.interfaces.utils import addClkRstn, propagateClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.scope import HlsScope
from hwt.code import If


class BramRead(Unit):
    """
    Sequentially read data from BRAM port.
    """

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.ADDR_WIDTH = Param(4)
        self.DATA_WIDTH = Param(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._paramsShared():
            self.dataOut = Handshaked()._m()
            self.ram: BramPort_withoutClk = BramPort_withoutClk()._m()

    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        i = Bits(self.ADDR_WIDTH).from_py(0)
        while BIT.from_py(1):
            d = hls.read(ram[i])
            hls.write(d, self.dataOut) 
            i += 1
        
    def _impl(self) -> None:
        hls = HlsScope(self)
        
        ram = BramArrayProxy(hls, self.ram, self.ram.dout._dtype[int(2 ** self.ADDR_WIDTH)])
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


class BramReadWithRom(Unit):

    def _config(self) -> None:
        BramRead._config(self)

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._paramsShared():
            self.dataOut = Handshaked()._m()
            self.reader = BramRead()

    def _impl(self) -> None:
        ITEMS = int(2**self.ADDR_WIDTH)
        rom = self._sig("rom", Bits(self.DATA_WIDTH)[ITEMS], [i + 1 for i in range(ITEMS)])
        r = self.reader
        self.dataOut(r.dataOut)
        
        If(self.clk._onRisingEdge(),
            If(r.ram.en,
               r.ram.dout(rom[r.ram.addr])
            )
        )
        propagateClkRstn(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    u = BramRead()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))