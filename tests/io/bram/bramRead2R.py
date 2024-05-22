#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import If
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOBramPort_noClk, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn, propagateClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.io.portGroups import MultiPortGroup
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.scope import HlsScope


class BramRead2R(HwModule):
    """
    Sequentially read data from 2 BRAM ports hidden by a single proxy.

    :note: dataOut0/ram0 reads first half, dataOut1/ram1 the second half
    """

    def _config(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(4)
        self.DATA_WIDTH = HwParam(64)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataOut0 = HwIODataRdVld()._m()
            self.dataOut1 = HwIODataRdVld()._m()
            self.ram0: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()
            self.ram1: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: BramArrayProxy):
        addrT = HBits(self.ADDR_WIDTH)
        i = HBits(self.ADDR_WIDTH - 1).from_py(0)
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
            for hwIO in (self.dataOut0, self.dataOut1, self.ram0, self.ram1):
                if rwNode.dst is hwIO:
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


class BramRead2RWithRom(HwModule):

    def _config(self) -> None:
        BramRead2R._config(self)

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataOut0 = HwIODataRdVld()._m()
            self.dataOut1 = HwIODataRdVld()._m()
            self.reader = BramRead2R()

    def _impl(self) -> None:
        ITEMS = int(2 ** self.ADDR_WIDTH)
        rom = self._sig("rom", HBits(self.DATA_WIDTH)[ITEMS], [i + 1 for i in range(ITEMS)])
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
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = BramRead2R()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
