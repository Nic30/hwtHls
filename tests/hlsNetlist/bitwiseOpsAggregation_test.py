#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from enum import Enum
from typing import Type

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import get_bit


class TREE_ORDER(Enum):
    PRE, IN, POST = range(3)


class HlsNetlistBitwiseOpsPreorder0HwModule(HwModule):

    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))

    def hwDeclr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        
        with self._hwParamsShared():
            self.i0 = HwIOSignal()
            self.i1 = HwIOSignal()
            self.i2 = HwIOSignal()
            self.o = HwIOSignal()._m()

    @staticmethod
    def model(i0, i1, i2):
        i0andI1 = BIT.from_py(None)
        while True:
            yield int(i0andI1 & next(i2))
            i0andI1 = next(i0) & next(i1)

    def mainThread(self, netlist: HlsNetlistCtx, treeOrder:TREE_ORDER):
        elm = ArchElementPipeline(netlist, "p0", "p0_")
        netlist.addNode(elm)
        i0 = HlsNetNodeRead(netlist, self.i0)
        i1 = HlsNetNodeRead(netlist, self.i1)
        i2 = HlsNetNodeRead(netlist, self.i2)
        elm.addNodes([i0, i1, i2])
        
        # scheduling offset 1clk for i2 from i1
        i0.getOrderingOutPort().connectHlsIn(i1._addInput("orderingIn"))
        lat = HlsNetNodeDelayClkTick(netlist, HVoidOrdering, 1)
        elm.addNode(lat)
        i1.getOrderingOutPort().connectHlsIn(lat._inputs[0])
        lat._outputs[0].connectHlsIn(i2._addInput("orderingIn"))

        o = HlsNetNodeWrite(netlist, self.o)
        elm.addNode(o)
        b = elm.builder
        if treeOrder == TREE_ORDER.PRE:
            i0andI1 = b.buildAnd(i0._outputs[0], i1._outputs[0])
            i0andI1andI2 = b.buildAnd(i0andI1, i2._outputs[0])

        elif treeOrder == TREE_ORDER.IN:
            i0andI2 = b.buildAnd(i0._outputs[0], i2._outputs[0])
            i0andI1andI2 = b.buildAnd(i0andI2, i1._outputs[0])
            
        else:
            assert treeOrder == TREE_ORDER.POST
            i1andI2 = b.buildAnd(i1._outputs[0], i2._outputs[0])
            i0andI1andI2 = b.buildAnd(i1andI2, i0._outputs[0])
            
        i0andI1andI2.connectHlsIn(o._inputs[0])

    def hwImpl(self, treeOrder:TREE_ORDER=TREE_ORDER.PRE) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, lambda netlist: self.mainThread(netlist, treeOrder)))
        hls.compile()


class HlsNetlistBitwiseOpsInorder0HwModule(HlsNetlistBitwiseOpsPreorder0HwModule):

    def hwImpl(self) -> None:
        HlsNetlistBitwiseOpsPreorder0HwModule.hwImpl(self, treeOrder=TREE_ORDER.IN)


class HlsNetlistBitwiseOpsPostorder0HwModule(HlsNetlistBitwiseOpsPreorder0HwModule):

    def hwImpl(self) -> None:
        HlsNetlistBitwiseOpsPreorder0HwModule.hwImpl(self, treeOrder=TREE_ORDER.POST)


class HlsNetlistBitwiseOpsTC(SimTestCase):

    def _test_HlsNetlistBitwiseOps0HwModule(self, cls: Type[HlsNetlistBitwiseOpsPreorder0HwModule]):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        i0 = dut.i0._ag.data
        i1 = dut.i1._ag.data
        i2 = dut.i2._ag.data
        
        N = (1 << 3) * 2
        for i in range(N):
            i0.append(get_bit(i, 0))
            i1.append(get_bit(i, 1))
            i2.append(get_bit(i, 2))

        ref = []
        m = cls.model(iter(i0), iter(i1), iter(i2))
        for _ in range(N):
            ref.append(next(m))
        
        self.runSim(int((N + 1) * freq_to_period(dut.CLK_FREQ)))
    
        res = dut.o._ag.data
        self.assertValSequenceEqual(res, ref)

    def test_HlsNetlistBitwiseOpsPreorder0HwModule(self):
        self._test_HlsNetlistBitwiseOps0HwModule(HlsNetlistBitwiseOpsPreorder0HwModule)

    def test_HlsNetlistBitwiseOpsInorder0HwModule(self):
        self._test_HlsNetlistBitwiseOps0HwModule(HlsNetlistBitwiseOpsPreorder0HwModule)

    def test_HlsNetlistBitwiseOpsPostorder0HwModule(self):
        self._test_HlsNetlistBitwiseOps0HwModule(HlsNetlistBitwiseOpsPostorder0HwModule)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = HlsNetlistBitwiseOpsPostorder0HwModule()
    m.CLK_FREQ = int(100e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsNetlistBitwiseOpsTC("test_NetlistWireHwModuleRdSynced")])
    suite = testLoader.loadTestsFromTestCase(HlsNetlistBitwiseOpsTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
