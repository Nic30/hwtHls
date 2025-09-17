#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import If
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIOBramPort_noClk, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn, propagateClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.bram import IoProxyBram
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import \
    netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.scope import HlsScope
from pyMathBitPrecise.bit_utils import mask


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

        with self._hwParamsShared():
            self.dataOut = HwIODataRdVld()._m()
            self.ram: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: IoProxyBram):
        i = HBits(self.ADDR_WIDTH).from_py(0)
        while b1:
            d = hls.read(ram[i]).data
            hls.write(d, self.dataOut)
            i += 1

    def reduceOrdering(self, hls: HlsScope, thread: HlsThreadFromPy):
        """
        Allow loop execute new loop iteration as soon as "i" is available.
        (Do not wait until the read completes)
        """
        netlist = thread.netlist
        for rwNode in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if isinstance(rwNode, HlsNetNodeWrite):
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
        ram = IoProxyBram(hls, self.ram)
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

        with self._hwParamsShared():
            self.dataOut = HwIODataRdVld()._m()
            self.reader = BramRead()

    @override
    def hwImpl(self) -> None:
        ITEMS = int(2 ** self.ADDR_WIDTH)
        maxVal = mask(self.DATA_WIDTH) + 1
        rom = self._sig("rom", HBits(self.DATA_WIDTH)[ITEMS], [(i + 1) % maxVal for i in range(ITEMS)])
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
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = BramRead()
    m.DATA_WIDTH = 36
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
        llvmCliArgs=[#LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                    ],
        debugFilter=HlsDebugBundle.ALL_RELIABLE)))
