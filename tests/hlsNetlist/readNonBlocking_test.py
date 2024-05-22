#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.netlist import HlsThreadFromNetlist
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class ReadNonBlockingHwModule(HwModule):
    """
    In this example the HlsNetNodeRead+HlsNetNodeExplicitSync should be converted to non blocking HlsNetNodeRead
    and ._validNB should be used to drive output MUX
    """

    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.dataIn = HwIODataRdVld()
            self.dataOut = HwIODataRdVld()._m()

    def connectIo(self, netlist: HlsNetlistCtx):
        """
        if dataIn.vld:
            d = dataIn.read()
        else:
            d = 0
        dataOut.write(d)
        """
        b = netlist.builder

        r = HlsNetNodeRead(netlist, self.dataIn)
        r._isBlocking = False
        netlist.inputs.append(r)
        rOut = r._outputs[0]
        rVld = b.buildReadSync(rOut)
        t = rOut._dtype

        mux = b.buildMux(t, (rOut, rVld, t.from_py(0)))
        w = HlsNetNodeWrite(netlist, self.dataOut)
        netlist.outputs.append(w)
        link_hls_nodes(mux, w._inputs[0])

    def hwImpl(self) -> None:
        hls = HlsScope(self, self.CLK_FREQ)
        hls.addThread(HlsThreadFromNetlist(hls, self.connectIo))
        hls.compile()


class ReadNonBockingTC(SimTestCase):

    def test_ReadNonBlockingHwModule(self):
        dut = ReadNonBlockingHwModule()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.dataIn._ag.data.extend([1])
        t = int(freq_to_period(dut.CLK_FREQ)) * 4
        self.runSim(t)
        self.assertValSequenceEqual(dut.dataOut._ag.data, [1, 0, 0])

     
if __name__ == '__main__':
    import unittest

    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = ReadNonBlockingHwModule()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ReadNonBockingTC("test_ReadNonBlockingHwModule")])
    suite = testLoader.loadTestsFromTestCase(ReadNonBockingTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

