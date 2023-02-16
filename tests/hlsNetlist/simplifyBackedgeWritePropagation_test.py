#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from tests.baseSsaTest import BaseSsaTC
from hwtSimApi.utils import freq_to_period


class CycleDelayUnit(Unit):

    def _config(self) -> None:
        self.CLK_FREQ = Param(int(100e6))
        self.DATA_WIDTH = Param(8)

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.dataOut = Handshaked()._m()

    def connectIo(self, netlist: HlsNetlistCtx):
        """
        backedge = 9
        dataOut = backedge
        """
        b = netlist.builder
        backedge = HsStructIntf()
        backedge.T = self.dataOut.data._dtype
        self.backedge = backedge

        br = HlsNetNodeReadBackwardEdge(netlist, backedge)
        netlist.inputs.append(br)
        
        bw = HlsNetNodeWriteBackwardEdge(netlist, NOT_SPECIFIED, backedge)
        netlist.outputs.append(bw)
        c9 = b.buildConst(backedge.T.from_py(9))
        link_hls_nodes(c9, bw._inputs[0])
        bw.associate_read(br)
        
        w = HlsNetNodeWrite(netlist, NOT_SPECIFIED, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(br._outputs[0], w._inputs[0])

    def _impl(self) -> None:
        self.hls = hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.connectIo))
        hls.compile()


class HlsCycleDelayUnit(BaseSsaTC):
    __FILE__ = __file__

    def test_CycleDelayUnit(self, f=100e6):
        u = CycleDelayUnit()
        u.FREQ = int(f)
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        self.assertEqual(len(list(u.hls._threads[0].toHw.iterAllNodes())), 3)  # const 9, io cluster, write


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = CycleDelayUnit()
    u.CLK_FREQ = int(40e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    
    suite = unittest.TestSuite()
    # suite.addTest(HlsCycleDelayUnit('test_CycleDelayUnit'))
    suite.addTest(unittest.makeSuite(HlsCycleDelayUnit))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
