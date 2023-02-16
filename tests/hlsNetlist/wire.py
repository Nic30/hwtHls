#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.interfaces.std import VectSignal, Handshaked, VldSynced, RdSynced
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class HlsNetlistWireUnit(Unit):

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.DATA_WIDTH = Param(8)

    def _declr(self) -> None:
        self.dataIn = VectSignal(self.DATA_WIDTH)
        self.dataOut = VectSignal(self.DATA_WIDTH)._m()

    def connectIo(self, netlist: HlsNetlistCtx):
        r = HlsNetNodeRead(netlist, self.dataIn)
        w = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.dataOut)
        link_hls_nodes(r._outputs[0], w._inputs[0])
        netlist.inputs.append(r)
        netlist.outputs.append(w)

    def _impl(self) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.connectIo))
        hls.compile()


class HlsNetlistWireUnitHs(HlsNetlistWireUnit):

    def _declr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        
        with self._paramsShared():
            self.dataIn = Handshaked()
            self.dataOut = Handshaked()._m()


class HlsNetlistWireUnitVldSynced(HlsNetlistWireUnit):

    def _declr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        
        with self._paramsShared():
            self.dataIn = VldSynced()
            self.dataOut = VldSynced()._m()


class HlsNetlistWireUnitRdSynced(HlsNetlistWireUnit):

    def _declr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        
        with self._paramsShared():
            self.dataIn = RdSynced()
            self.dataOut = RdSynced()._m()


class HlsNetlistWireTC(SimTestCase):

    def test_HlsNetlistWireUnit(self, cls: Type[HlsNetlistWireUnit]=HlsNetlistWireUnit, extraTime=0):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        N = 4
        u.dataIn._ag.data.extend(range(N))
        self.runSim(int((N + extraTime) * freq_to_period(u.CLK_FREQ)))

        res = u.dataOut._ag.data
        self.assertValSequenceEqual(res, list(range(N)))

    def test_HlsNetlistWireUnitHs(self):
        self.test_HlsNetlistWireUnit(HlsNetlistWireUnitHs, extraTime=1)

    def test_HlsNetlistWireUnitVldSynced(self):
        self.test_HlsNetlistWireUnit(HlsNetlistWireUnitVldSynced, extraTime=1)

    def test_HlsNetlistWireUnitRdSynced(self):
        self.test_HlsNetlistWireUnit(HlsNetlistWireUnitRdSynced, extraTime=1)


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = HlsNetlistWireUnitHs()
    u.DATA_WIDTH = 32
    u.CLK_FREQ = int(40e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    suite = unittest.TestSuite()
    # suite.addTest(HlsNetlistWireTC('test_NetlistWireUnitRdSynced'))
    suite.addTest(unittest.makeSuite(HlsNetlistWireTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
