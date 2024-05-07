#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import If
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import BramPort_withoutClk, Handshaked
from hwt.interfaces.utils import addClkRstn, propagateClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.io.portGroups import MultiPortGroup
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.scope import HlsScope


class BramRead2R(Unit):
    """
    Sequentially read data from 2 BRAM ports hidden by a single proxy.

    :note: dataOut0/ram0 reads first half, dataOut1/ram1 the second half
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
        addrT = Bits(self.ADDR_WIDTH)
        i = Bits(self.ADDR_WIDTH - 1).from_py(0)
        while BIT.from_py(1):
            iAsAddr = i._reinterpret_cast(addrT)
            d0 = hls.read(ram[iAsAddr]).data
            d1 = hls.read(ram[iAsAddr + (1 << (self.ADDR_WIDTH - 1))]).data
            hls.write(d0, self.dataOut0)
            hls.write(d1, self.dataOut1)
            i += 1

    def reduceOrdering(self, hls: HlsScope, thread: HlsThreadFromPy):
        """
        Allow loop execute new loop iteration as soon as "i" is available.
        (Do not wait until the read completes)
        """
        netlist = thread.toHw
        for rwNode in netlist.outputs:
            rwNode: HlsNetNodeWrite
            for intf in (self.dataOut0, self.dataOut1, self.ram0, self.ram1):
                if rwNode.dst is intf:
                    netlistExplicitSyncDisconnectFromOrderingChain(DebugTracer(None), rwNode, None,
                                                                   disconnectPredecessors=False,
                                                                   disconnectSuccesors=True)
                    break

    def _impl(self) -> None:
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, MultiPortGroup((self.ram0, self.ram1)))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        mainThread.netlistCallbacks.append(self.reduceOrdering)
        hls.addThread(mainThread)
        hls.compile()


class BramRead2RWithRom(Unit):

    def _config(self) -> None:
        BramRead2R._config(self)

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._paramsShared():
            self.dataOut0 = Handshaked()._m()
            self.dataOut1 = Handshaked()._m()
            self.reader = BramRead2R()

    def _impl(self) -> None:
        ITEMS = int(2 ** self.ADDR_WIDTH)
        rom = self._sig("rom", Bits(self.DATA_WIDTH)[ITEMS], [i + 1 for i in range(ITEMS)])
        r = self.reader
        self.dataOut0(r.dataOut0)
        self.dataOut1(r.dataOut1)

        for ramPort in (r.ram0, r.ram1):
            If(self.clk._onRisingEdge(),
                If(ramPort.en,
                   ramPort.dout(rom[ramPort.addr])
                )
            )
        propagateClkRstn(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = BramRead2R()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
