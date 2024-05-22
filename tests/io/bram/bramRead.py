#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import If
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOBramPort_noClk, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn, propagateClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import \
    netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.scope import HlsScope


class BramRead(HwModule):
    """
    Sequentially read data from BRAM port.
    """

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(4)
        self.DATA_WIDTH = HwParam(64)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataOut = HwIODataRdVld()._m()
            self.ram: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        i = HBits(self.ADDR_WIDTH).from_py(0)
        while BIT.from_py(1):
            d = hls.read(ram[i]).data
            hls.write(d, self.dataOut)
            i += 1

    def reduceOrdering(self, hls: HlsScope, thread: HlsThreadFromPy):
        """
        Allow loop execute new loop iteration as soon as "i" is available.
        (Do not wait until the read completes)
        """
        netlist = thread.toHw
        for rwNode in netlist.outputs:
            rwNode: HlsNetNodeWrite
            for hwIO in (self.dataOut, self.ram):
                if rwNode.dst is hwIO:
                    netlistExplicitSyncDisconnectFromOrderingChain(DebugTracer(None), rwNode, None,
                                                                   disconnectPredecessors=False,
                                                                   disconnectSuccesors=True)
                    break

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, self.ram)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        mainThread.netlistCallbacks.append(self.reduceOrdering)

        hls.addThread(mainThread)
        hls.compile()


class BramReadWithRom(HwModule):

    @override
    def hwConfig(self) -> None:
        BramRead.hwConfig(self)

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataOut = HwIODataRdVld()._m()
            self.reader = BramRead()

    @override
    def hwImpl(self) -> None:
        ITEMS = int(2 ** self.ADDR_WIDTH)
        rom = self._sig("rom", HBits(self.DATA_WIDTH)[ITEMS], [i + 1 for i in range(ITEMS)])
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
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = BramRead()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
