#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from tests.baseSsaTest import BaseSsaTC


class CycleDelayHwModule(HwModule):

    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.dataOut = HwIODataRdVld()._m()

    def connectIo(self, netlist: HlsNetlistCtx):
        """
        backedge = 9
        dataOut = backedge
        """
        elm = ArchElementPipeline(netlist, self.__class__.__name__, self.__class__.__name__ + "_")
        netlist.addNode(elm)
        b = elm.builder
        T = self.dataOut.data._dtype
        br = HlsNetNodeReadBackedge(netlist, T)
        elm.addNode(br)

        bw = HlsNetNodeWriteBackedge(netlist)
        elm.addNode(bw)
        c9 = b.buildConst(T.from_py(9))
        c9.connectHlsIn(bw._portSrc)
        bw.associateRead(br)

        w = HlsNetNodeWrite(netlist, self.dataOut)
        elm.addNode(w)
        br._portDataOut.connectHlsIn(w._portSrc)

    def hwImpl(self) -> None:
        self.hls = hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.connectIo))
        hls.compile()


class HlsCycleDelayHwModule(BaseSsaTC):
    __FILE__ = __file__

    def test_CycleDelayHwModule(self, f=100e6):
        dut = CycleDelayHwModule()
        dut.FREQ = int(f)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        nodes = list(dut.hls._threads[0].netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT))
        self.assertEqual(len(nodes), 2, nodes)  # const 9, write


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = CycleDelayHwModule()
    m.CLK_FREQ = int(40e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsCycleDelayHwModule("test_CycleDelayHwModule")])
    suite = testLoader.loadTestsFromTestCase(HlsCycleDelayHwModule)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
