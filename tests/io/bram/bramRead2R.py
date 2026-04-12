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
from hwtHls.io.portGroups import MultiPortGroup
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.scope import HlsScope
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS


class BramRead2R(HwModule):
    """
    Sequentially read data from 2 BRAM ports hidden by a single proxy.

    :note: dataOut0/ram0 reads first half, dataOut1/ram1 the second half
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
            self.dataOut0 = HwIODataRdVld()._m()
            self.dataOut1 = HwIODataRdVld()._m()
            self.ram0: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()
            self.ram1: HwIOBramPort_noClk = HwIOBramPort_noClk()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: IoProxyBram):
        addrT = HBits(self.ADDR_WIDTH)
        i = HBits(self.ADDR_WIDTH - 1).from_py(0)
        while b1:
            iAsAddr = i._reinterpret_cast(addrT)
            d0 = ram.read(iAsAddr).data
            d1 = ram.read(iAsAddr + (1 << (self.ADDR_WIDTH - 1))).data
            # :note: mayBecomeFlushable=False would lead to much more simple circuit, but
            #  it would make dataOut0, dataOut1 control to depend on each other,
            #  it would allow  dataOut0, dataOut1 only to be read togheter
            hls.write(d0, self.dataOut0)
            hls.write(d1, self.dataOut1)
            i += 1

    def reduceOrdering(self, hls: HlsScope, thread: HlsThreadFromPy, ramIo: MultiPortGroup):
        """
        Allow loop execute new loop iteration as soon as "i" is available.
        (Do not wait until the read completes)
        """
        netlist = thread.netlist
        for rwNode in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if isinstance(rwNode, HlsNetNodeWrite):
                rwNode: HlsNetNodeWrite
                assert rwNode.dst not in (self.ram0, self.ram1)
                for hwIO in (self.dataOut0, self.dataOut1, ramIo):
                    if rwNode.dst is hwIO:
                        netlistExplicitSyncDisconnectFromOrderingChain(DebugTracer(None), rwNode, None,
                                                                       disconnectPredecessors=False,
                                                                       disconnectSuccesors=True)
                        break

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        ramIo = MultiPortGroup((self.ram0, self.ram1))
        ram = IoProxyBram(hls, ramIo)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        mainThread.netlistCallbacks.append(lambda hls, thread: self.reduceOrdering(hls, thread, ramIo))
        hls.addThread(mainThread)
        hls.compile()


class BramRead2RWithRom(HwModule):

    @override
    def hwConfig(self) -> None:
        BramRead2R.hwConfig(self)

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        with self._hwParamsShared():
            self.dataOut0 = HwIODataRdVld()._m()
            self.dataOut1 = HwIODataRdVld()._m()
            self.reader = BramRead2R()

    @override
    def hwImpl(self) -> None:
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
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = BramRead2RWithRom()
    p = VirtualHlsPlatform(
        llvmCliArgs=[
            # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
        ],
        debugFilter=HlsDebugBundle.ALL_RELIABLE
    )
    print(to_rtl_str(m, target_platform=p))
