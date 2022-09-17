from enum import Enum
from typing import Type

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Signal
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.orderable import HOrderingVoidT
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import get_bit


class TREE_ORDER(Enum):
    PRE, IN, POST = range(3)


class HlsNetlistBitwiseOpsPreorder0Unit(Unit):

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self) -> None:
        # added because of sim agent
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        
        with self._paramsShared():
            self.i0 = Signal()
            self.i1 = Signal()
            self.i2 = Signal()
            self.o = Signal()._m()

    @staticmethod
    def model(i0, i1, i2):
        i0andI1 = BIT.from_py(None)
        while True:
            yield int(i0andI1 & next(i2))
            i0andI1 = next(i0) & next(i1)

    def mainThread(self, netlist: HlsNetlistCtx, treeOrder:TREE_ORDER):
        i0 = HlsNetNodeRead(netlist, self.i0)
        i1 = HlsNetNodeRead(netlist, self.i1)
        i2 = HlsNetNodeRead(netlist, self.i2)
        
        # scheduling offset 1clk for i2 from i1
        link_hls_nodes(i0.getOrderingOutPort(), i1._addInput("orderingIn"))
        lat = HlsNetNodeDelayClkTick(netlist, 1, HOrderingVoidT)
        netlist.nodes.append(lat)
        link_hls_nodes(i1.getOrderingOutPort(), lat._inputs[0])
        link_hls_nodes(lat._outputs[0], i2._addInput("orderingIn"))
        netlist.inputs.extend([i0, i1, i2])
        
        o = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.o)
        netlist.outputs.append(o)
        b = HlsNetlistBuilder(netlist)

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
            
        link_hls_nodes(i0andI1andI2, o._inputs[0])

    def _impl(self, treeOrder:TREE_ORDER=TREE_ORDER.PRE) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, lambda netlist: self.mainThread(netlist, treeOrder)))
        hls.compile()


class HlsNetlistBitwiseOpsInorder0Unit(HlsNetlistBitwiseOpsPreorder0Unit):

    def _impl(self) -> None:
        HlsNetlistBitwiseOpsPreorder0Unit._impl(self, treeOrder=TREE_ORDER.IN)


class HlsNetlistBitwiseOpsPostorder0Unit(HlsNetlistBitwiseOpsPreorder0Unit):

    def _impl(self) -> None:
        HlsNetlistBitwiseOpsPreorder0Unit._impl(self, treeOrder=TREE_ORDER.POST)


class HlsNetlistBitwiseOpsTC(SimTestCase):

    def _test_HlsNetlistBitwiseOps0Unit(self, cls: Type[HlsNetlistBitwiseOpsPreorder0Unit]):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        i0 = u.i0._ag.data
        i1 = u.i1._ag.data
        i2 = u.i2._ag.data
        
        N = (1 << 3) * 2
        for i in range(N):
            i0.append(get_bit(i, 0))
            i1.append(get_bit(i, 1))
            i2.append(get_bit(i, 2))

        ref = []
        m = cls.model(iter(i0), iter(i1), iter(i2))
        for _ in range(N):
            ref.append(next(m))
        
        self.runSim(int((N + 1) * freq_to_period(u.CLK_FREQ)))
    
        res = u.o._ag.data
        self.assertValSequenceEqual(res, ref)

    def test_HlsNetlistBitwiseOpsPreorder0Unit(self):
        self._test_HlsNetlistBitwiseOps0Unit(HlsNetlistBitwiseOpsPreorder0Unit)

    def test_HlsNetlistBitwiseOpsInorder0Unit(self):
        self._test_HlsNetlistBitwiseOps0Unit(HlsNetlistBitwiseOpsPreorder0Unit)

    def test_HlsNetlistBitwiseOpsPostorder0Unit(self):
        self._test_HlsNetlistBitwiseOps0Unit(HlsNetlistBitwiseOpsPostorder0Unit)


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    u = HlsNetlistBitwiseOpsPostorder0Unit()
    u.CLK_FREQ = int(100e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))

    suite = unittest.TestSuite()
    # suite.addTest(HlsNetlistBitwiseOpsTC('test_NetlistWireUnitRdSynced'))
    suite.addTest(unittest.makeSuite(HlsNetlistBitwiseOpsTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
