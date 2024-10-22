#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.hwIOs.std import HwIOVectSignal, HwIODataRdVld, HwIODataVld, HwIODataRd
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class HlsNetlistWireHwModule(HwModule):

    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    def hwDeclr(self) -> None:
        self.dataIn = HwIOVectSignal(self.DATA_WIDTH)
        self.dataOut = HwIOVectSignal(self.DATA_WIDTH)._m()

    def connectIo(self, netlist: HlsNetlistCtx):
        elm = ArchElementPipeline(netlist, "p0", "p0_")
        netlist.addNode(elm)
        r = HlsNetNodeRead(netlist, self.dataIn)
        w = HlsNetNodeWrite(netlist, self.dataOut)
        r._portDataOut.connectHlsIn(w._portSrc)
        w.addControlSerialExtraCond(r.getValidNB())
        elm.addNodes((r, w))

    def hwImpl(self) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.connectIo))
        hls.compile()


class HlsNetlistWireHwModuleHs(HlsNetlistWireHwModule):

    def hwDeclr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataIn = HwIODataRdVld()
            self.dataOut = HwIODataRdVld()._m()


class HlsNetlistWireHwModuleVldSynced(HlsNetlistWireHwModule):

    def hwDeclr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataIn = HwIODataVld()
            self.dataOut = HwIODataVld()._m()


class HlsNetlistWireHwModuleRdSynced(HlsNetlistWireHwModule):

    def hwDeclr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        with self._hwParamsShared():
            self.dataIn = HwIODataRd()
            self.dataOut = HwIODataRd()._m()


class HlsNetlistWireTC(SimTestCase):

    def test_HlsNetlistWireHwModule(self, cls: Type[HlsNetlistWireHwModule]=HlsNetlistWireHwModule,
                                    extraTime=0, target_platform=VirtualHlsPlatform()):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=target_platform)
        N = 4
        dut.dataIn._ag.data.extend(range(N))
        self.runSim(int((N + extraTime) * freq_to_period(dut.CLK_FREQ)))

        res = dut.dataOut._ag.data
        self.assertValSequenceEqual(res, list(range(N)))

    def test_HlsNetlistWireHwModuleHs(self):
        self.test_HlsNetlistWireHwModule(HlsNetlistWireHwModuleHs, extraTime=1)

    def test_HlsNetlistWireHwModuleVldSynced(self):
        self.test_HlsNetlistWireHwModule(HlsNetlistWireHwModuleVldSynced, extraTime=1)

    def test_HlsNetlistWireHwModuleRdSynced(self):
        self.test_HlsNetlistWireHwModule(HlsNetlistWireHwModuleRdSynced, extraTime=1)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = HlsNetlistWireHwModule()
    m.DATA_WIDTH = 32
    m.CLK_FREQ = int(40e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistWireTC("test_NetlistWireHwModuleRdSynced")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistWireTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
