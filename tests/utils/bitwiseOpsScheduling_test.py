#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.aggregateBitwiseOps import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistPassDumpNodesDot
from hwtHls.netlist.translation.dumpSchedulingJson import HlsNetlistPassDumpSchedulingJson
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.platform.fileUtils import outputFileGetter
from hwt.interfaces.std import VectSignal


class BitwiseOpsScheduling_TC(SimTestCase):

    def test_3not_200MHz(self):
        self._test_3not(200e6)

    def test_3not_400MHz(self):
        self._test_3not(400e6)

    def _test_3not(self, freq:float):
        platform = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
        net = HlsNetlistCtx(None, freq, f"3not{int(freq//1e6)}Mhz", platform=platform)
        net.builder = HlsNetlistBuilder(net)
        t = Bits(8)
        r = HlsNetNodeRead(net, VectSignal(8), t, name="r0")
        net.inputs.append(r)
        n0 = HlsNetNodeOperator(net, AllOps.NOT, 1, t, "n0")
        n1 = HlsNetNodeOperator(net, AllOps.NOT, 1, t, "n1")
        n2 = HlsNetNodeOperator(net, AllOps.NOT, 1, t, "n2")
        net.nodes.extend((n0, n1, n2))

        w = HlsNetNodeWrite(net, None, VectSignal(8), name="w0")
        net.outputs.append(w)

        prev = r
        for n in (n0, n1, n2, w):
            link_hls_nodes(prev._outputs[0], n._inputs[0])
            prev = n

        HlsNetlistPassAggregateBitwiseOps().apply(None, net)
        # HlsNetlistPassDumpNodesDot(outputFileGetter("tmp", ".nodes.dot")).apply(None, net)
        net.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
        # HlsNetlistPassDumpSchedulingJson(outputFileGetter("tmp", ".hwschedule.json")).apply(None, net)

    def test_2not1and_200MHz(self):
        self._test_2not1and(200e6)

    def test_2not1and_400MHz(self):
        self._test_2not1and(400e6)

    def _test_2not1and(self, freq:float):
        platform = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
        net = HlsNetlistCtx(None, freq, f"2not1and{int(freq//1e6)}Mhz", platform=platform)
        net.builder = HlsNetlistBuilder(net)
        t = Bits(8)
        r0 = HlsNetNodeRead(net, VectSignal(8), t, name="r0")
        r1 = HlsNetNodeRead(net, VectSignal(8), t, name="r1")
        net.inputs.extend((r0, r1))
        n0 = HlsNetNodeOperator(net, AllOps.NOT, 1, t, "n0")
        n1 = HlsNetNodeOperator(net, AllOps.NOT, 1, t, "n1")
        n2 = HlsNetNodeOperator(net, AllOps.AND, 2, t, "n2")
        net.nodes.extend((n0, n1, n2))

        w = HlsNetNodeWrite(net, None, VectSignal(8), name="w0")
        net.outputs.append(w)

        prev = r0
        for n in (n0, n1, n2, w):
            link_hls_nodes(prev._outputs[0], n._inputs[0])
            prev = n
        link_hls_nodes(r1._outputs[0], n2._inputs[1])

        HlsNetlistPassAggregateBitwiseOps().apply(None, net)
        HlsNetlistPassDumpNodesDot(outputFileGetter("tmp", ".nodes.dot")).apply(None, net)
        net.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
        HlsNetlistPassDumpSchedulingJson(outputFileGetter("tmp", ".hwschedule.json")).apply(None, net)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    #suite = unittest.TestSuite([BitwiseOpsScheduling_TC('test_2not1and_400MHz'), ])
    suite = testLoader.loadTestsFromTestCase(BitwiseOpsScheduling_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
