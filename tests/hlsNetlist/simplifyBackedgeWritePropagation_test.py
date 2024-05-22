#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from tests.baseSsaTest import BaseSsaTC


class CycleDelayHwModule(HwModule):

    def _config(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.dataOut = HwIODataRdVld()._m()

    def connectIo(self, netlist: HlsNetlistCtx):
        """
        backedge = 9
        dataOut = backedge
        """
        b = netlist.builder
        T = self.dataOut.data._dtype
        br = HlsNetNodeReadBackedge(netlist, T)
        netlist.inputs.append(br)

        bw = HlsNetNodeWriteBackedge(netlist)
        netlist.outputs.append(bw)
        c9 = b.buildConst(T.from_py(9))
        link_hls_nodes(c9, bw._inputs[0])
        bw.associateRead(br)

        w = HlsNetNodeWrite(netlist, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(br._outputs[0], w._inputs[0])

    def _impl(self) -> None:
        self.hls = hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.connectIo))
        hls.compile()


class HlsCycleDelayHwModule(BaseSsaTC):
    __FILE__ = __file__

    def test_CycleDelayHwModule(self, f=100e6):
        dut = CycleDelayHwModule()
        dut.FREQ = int(f)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self.assertEqual(len(list(dut.hls._threads[0].toHw.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT))), 4)  # const 9, 2xio cluster, write


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
