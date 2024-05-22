#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

from hwt.hwIOs.std import HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistPassDumpNodesDot
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from ipCorePackager.constants import DIRECTION


class HlsNetlistSyncIsland0HwModule(HwModule):
    """
    o.write(i0.read())
    """

    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.TEST_CASE: Optional[SimTestCase] = None

    def hwDeclr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.i0 = HwIOSignal()
            self.o = HwIOSignal()._m()

    def mainThread(self, netlist: HlsNetlistCtx):
        i0 = HlsNetNodeRead(netlist, self.i0)

        # scheduling offset 1clk for i2 from i1
        netlist.inputs.extend([i0, ])

        o = HlsNetNodeWrite(netlist, self.o)
        netlist.outputs.append(o)
        link_hls_nodes(i0._outputs[0], o._inputs[0])
        reachDb: HlsNetlistAnalysisPassReachability = netlist.getAnalysis(HlsNetlistAnalysisPassReachability)

        tc: SimTestCase = self.TEST_CASE
        if tc is not None:
            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(i0, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [i0, ])
            tc.assertSequenceEqual(outputs, [o, ])

            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(o, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [o, ])
            tc.assertSequenceEqual(outputs, set())

        netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability)

    def hwImpl(self) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.mainThread))
        hls.compile()


class HlsNetlistSyncIsland1HwModule(HlsNetlistSyncIsland0HwModule):
    """
    read0 -> wf0 .. rf0 -> write
    """

    def mainThread(self, netlist: HlsNetlistCtx):
        i0 = HlsNetNodeRead(netlist, self.i0)

        # scheduling offset 1clk for i2 from i1
        netlist.inputs.extend([i0, ])

        fw, fr, frOut = HlsNetNodeWriteForwardedge.createPredSucPair(netlist, "f", i0._outputs[0])

        o = HlsNetNodeWrite(netlist, self.o)
        netlist.outputs.append(o)
        link_hls_nodes(frOut, o._inputs[0])
        reachDb: HlsNetlistAnalysisPassReachability = netlist.getAnalysis(HlsNetlistAnalysisPassReachability)

        tc: SimTestCase = self.TEST_CASE
        if tc is not None:
            # HlsNetlistPassDumpNodesDot(outputFileGetter("tmp", "nodes.dot")).runOnHlsNetlist(netlist)
            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(i0, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [i0, ])
            tc.assertSequenceEqual(outputs, [fw])

            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(fw, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [fw, ])
            tc.assertSequenceEqual(outputs, [ ])

            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(fr, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [fr, ])
            tc.assertSequenceEqual(outputs, [o, ])

            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(o, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [o, ])
            tc.assertSequenceEqual(outputs, set())

        netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability)


class HlsNetlistSyncIsland2HwModule(HlsNetlistSyncIsland0HwModule):
    """
    read0 -> and -> sync -> write
    read1 ---^
    """

    def hwDeclr(self) -> None:
        HlsNetlistSyncIsland0HwModule.hwDeclr(self)
        with self._hwParamsShared():
            self.i1 = HwIOSignal()

    def mainThread(self, netlist: HlsNetlistCtx):
        i0 = HlsNetNodeRead(netlist, self.i0)
        i1 = HlsNetNodeRead(netlist, self.i1)

        # scheduling offset 1clk for i2 from i1
        netlist.inputs.extend([i0, i1])
        b: HlsNetlistBuilder = netlist.builder
        i0andI1 = b.buildAnd(i0._outputs[0], i1._outputs[0])

        fw, fr, frOut = HlsNetNodeWriteForwardedge.createPredSucPair(netlist, "f", i0andI1)

        o = HlsNetNodeWrite(netlist, self.o)
        netlist.outputs.append(o)
        link_hls_nodes(frOut, o._inputs[0])
        reachDb: HlsNetlistAnalysisPassReachability = netlist.getAnalysis(HlsNetlistAnalysisPassReachability)

        tc: SimTestCase = self.TEST_CASE
        if tc is not None:
            # HlsNetlistPassDumpNodesDot(outputFileGetter("tmp", "nodes.dot")).runOnHlsNetlist(netlist)
            inputs, outputs, nodes = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(i0, DIRECTION.IN, reachDb)
            # sync is input because the dependency was changed to void
            tc.assertSequenceEqual(inputs, [i0, i1])
            tc.assertSequenceEqual(outputs, [fw, ])
            tc.assertSequenceEqual(nodes, [i0andI1.obj, ])

            inputs, outputs, nodes = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(i1, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [i1, i0])
            tc.assertSequenceEqual(outputs, [fw, ])
            tc.assertSequenceEqual(nodes, [i0andI1.obj, ])

            inputs, outputs, nodes = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(fr, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [fr])
            tc.assertSequenceEqual(outputs, [o])
            tc.assertSequenceEqual(nodes, [ ])

            inputs, outputs, nodes = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(o, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [o, ])
            tc.assertSequenceEqual(outputs, set())
        netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability)


class HlsNetlistDiscoverSyncIslandTC(SimTestCase):

    def test_HlsNetlistSyncIsland0HwModule(self, cls=HlsNetlistSyncIsland0HwModule):
        dut = cls()
        dut.TEST_CASE = self
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

    def test_HlsNetlistSyncIsland1HwModule(self):
        self.test_HlsNetlistSyncIsland0HwModule(HlsNetlistSyncIsland1HwModule)

    def test_HlsNetlistSyncIsland2HwModule(self):
        self.test_HlsNetlistSyncIsland0HwModule(HlsNetlistSyncIsland2HwModule)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = HlsNetlistSyncIsland2HwModule()
    m.CLK_FREQ = int(100e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistDiscoverSyncIslandTC("test_HlsNetlistSyncIsland2HwModule")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistDiscoverSyncIslandTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
