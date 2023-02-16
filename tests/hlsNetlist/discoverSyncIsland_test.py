#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

from hwt.interfaces.std import Signal
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from ipCorePackager.constants import DIRECTION


class HlsNetlistSyncIsland0Unit(Unit):
    """
    o.write(i0.read())
    """

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.TEST_CASE: Optional[SimTestCase] = None

    def _declr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        
        with self._paramsShared():
            self.i0 = Signal()
            self.o = Signal()._m()

    def mainThread(self, netlist: HlsNetlistCtx):
        i0 = HlsNetNodeRead(netlist, self.i0)
        
        # scheduling offset 1clk for i2 from i1
        netlist.inputs.extend([i0, ])
        
        o = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.o)
        netlist.outputs.append(o)
        link_hls_nodes(i0._outputs[0], o._inputs[0])
        reachDb: HlsNetlistAnalysisPassReachabilility = netlist.getAnalysis(HlsNetlistAnalysisPassReachabilility)
        
        tc: SimTestCase = self.TEST_CASE
        if tc is not None:
            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(i0, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [i0, ])
            tc.assertSequenceEqual(outputs, [o, ])
    
            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(o, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [o, ])
            tc.assertSequenceEqual(outputs, set())

    def _impl(self) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.mainThread))
        hls.compile()


class HlsNetlistSyncIsland1Unit(HlsNetlistSyncIsland0Unit):
    """
    read0 -> sync -> write
    """
    
    def mainThread(self, netlist: HlsNetlistCtx):
        i0 = HlsNetNodeRead(netlist, self.i0)
        
        # scheduling offset 1clk for i2 from i1
        netlist.inputs.extend([i0, ])
        
        sync = HlsNetNodeExplicitSync(netlist, i0._outputs[0]._dtype)
        netlist.nodes.append(sync)
        link_hls_nodes(i0._outputs[0], sync._inputs[0])
        
        o = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.o)
        netlist.outputs.append(o)
        link_hls_nodes(sync._outputs[0], o._inputs[0])
        reachDb: HlsNetlistAnalysisPassReachabilility = netlist.getAnalysis(HlsNetlistAnalysisPassReachabilility)
        
        tc: SimTestCase = self.TEST_CASE
        if tc is not None:
            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(i0, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [i0, ])
            tc.assertSequenceEqual(outputs, [sync, ])

            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(sync, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [sync, ])
            tc.assertSequenceEqual(outputs, [o, ])
    
            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(o, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [o, ])
            tc.assertSequenceEqual(outputs, set())


class HlsNetlistSyncIsland2Unit(HlsNetlistSyncIsland0Unit):
    """
    read0 -> and -> sync -> write
    read1 ---^
    """

    def _declr(self) -> None:
        HlsNetlistSyncIsland0Unit._declr(self)
        with self._paramsShared():
            self.i1 = Signal()

    def mainThread(self, netlist: HlsNetlistCtx):
        i0 = HlsNetNodeRead(netlist, self.i0)
        i1 = HlsNetNodeRead(netlist, self.i1)
        
        # scheduling offset 1clk for i2 from i1
        netlist.inputs.extend([i0, i1])
        b: HlsNetlistBuilder = netlist.builder
        i0andI1 = b.buildAnd(i0._outputs[0], i1._outputs[0])

        sync = HlsNetNodeExplicitSync(netlist, i0andI1._dtype)
        netlist.nodes.append(sync)
        link_hls_nodes(i0andI1, sync._inputs[0])
        
        o = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.o)
        netlist.outputs.append(o)
        link_hls_nodes(sync._outputs[0], o._inputs[0])
        reachDb: HlsNetlistAnalysisPassReachabilility = netlist.getAnalysis(HlsNetlistAnalysisPassReachabilility)
        
        tc: SimTestCase = self.TEST_CASE
        if tc is not None:
            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(i0, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [i0, i1])
            tc.assertSequenceEqual(outputs, [sync, ])

            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(i1, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [i1, i0])
            tc.assertSequenceEqual(outputs, [sync, ])

            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(sync, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [sync, ])
            tc.assertSequenceEqual(outputs, [o, ])
    
            inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(o, DIRECTION.IN, reachDb)
            tc.assertSequenceEqual(inputs, [o, ])
            tc.assertSequenceEqual(outputs, set())


class HlsNetlistDiscoverSyncIslandTC(SimTestCase):

    def test_HlsNetlistSyncIsland0Unit(self, cls=HlsNetlistSyncIsland0Unit):
        u = cls()
        u.TEST_CASE = self
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
    
    def test_HlsNetlistSyncIsland1Unit(self):
        self.test_HlsNetlistSyncIsland0Unit(HlsNetlistSyncIsland1Unit)

    def test_HlsNetlistSyncIsland2Unit(self):
        self.test_HlsNetlistSyncIsland0Unit(HlsNetlistSyncIsland2Unit)


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = HlsNetlistSyncIsland2Unit()
    u.CLK_FREQ = int(100e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    suite = unittest.TestSuite()
    # suite.addTest(HlsNetlistDiscoverSyncIslandTC('test_HlsNetlistSyncIsland2Unit'))
    suite.addTest(unittest.makeSuite(HlsNetlistDiscoverSyncIslandTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
