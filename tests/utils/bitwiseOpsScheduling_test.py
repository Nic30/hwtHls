#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIOVectSignal
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.aggregateBitwiseOps import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistAnalysisPassDumpNodesDot
from hwtHls.netlist.translation.dumpSchedulingJson import HlsNetlistAnalysisPassDumpSchedulingJson
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform


class BitwiseOpsScheduling_TC(SimTestCase):

    def test_3not_200MHz(self):
        self._test_3not(200e6)

    def test_3not_400MHz(self):
        self._test_3not(400e6)

    def _test_3not(self, freq:float):
        platform = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
        net = HlsNetlistCtx(None, freq, f"3not{int(freq//1e6)}Mhz", {}, platform=platform)
        net.builder = HlsNetlistBuilder(net)
        t = HBits(8)
        r = HlsNetNodeRead(net, HwIOVectSignal(8), t, name="r0")
        net.addNode(r)
        n0 = HlsNetNodeOperator(net, HwtOps.NOT, 1, t, "n0")
        n1 = HlsNetNodeOperator(net, HwtOps.NOT, 1, t, "n1")
        n2 = HlsNetNodeOperator(net, HwtOps.NOT, 1, t, "n2")
        net.addNodes((n0, n1, n2))

        w = HlsNetNodeWrite(net, HwIOVectSignal(8), name="w0")
        net.addNode(w)

        prev = r
        for n in (n0, n1, n2, w):
            prev._outputs[0].connectHlsIn(n._inputs[0])
            prev = n

        HlsNetlistPassAggregateBitwiseOps().runOnHlsNetlist(net)
        # HlsNetlistAnalysisPassDumpNodesDot(outputFileGetter("tmp", ".nodes.dot")).runOnHlsNetlist(net)
        net.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
        # HlsNetlistAnalysisPassDumpSchedulingJson(outputFileGetter("tmp", ".hwschedule.json")).runOnHlsNetlist(net)

    def test_2not1and_200MHz(self):
        self._test_2not1and(200e6)

    def test_2not1and_400MHz(self):
        self._test_2not1and(400e6)

    def _test_2not1and(self, freq:float):
        platform = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
        net = HlsNetlistCtx(None, freq, f"2not1and{int(freq//1e6)}Mhz", {}, platform=platform)
        net.builder = HlsNetlistBuilder(net)
        t = HBits(8)
        r0 = HlsNetNodeRead(net, HwIOVectSignal(8), t, name="r0")
        r1 = HlsNetNodeRead(net, HwIOVectSignal(8), t, name="r1")
        net.addNodes((r0, r1))
        n0 = HlsNetNodeOperator(net, HwtOps.NOT, 1, t, "n0")
        n1 = HlsNetNodeOperator(net, HwtOps.NOT, 1, t, "n1")
        n2 = HlsNetNodeOperator(net, HwtOps.AND, 2, t, "n2")
        net.addNodes((n0, n1, n2))

        w = HlsNetNodeWrite(net, HwIOVectSignal(8), name="w0")
        net.addNode(w)

        prev = r0
        for n in (n0, n1, n2, w):
            prev._outputs[0].connectHlsIn(n._inputs[0])
            prev = n
        r1._outputs[0].connectHlsIn(n2._inputs[1])

        HlsNetlistPassAggregateBitwiseOps().runOnHlsNetlist(net)
        #HlsNetlistAnalysisPassDumpNodesDot(outputFileGetter("tmp", ".nodes.dot")).runOnHlsNetlist(net)
        net.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
        #HlsNetlistAnalysisPassDumpSchedulingJson(outputFileGetter("tmp", ".hwschedule.json")).runOnHlsNetlist(net)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    #suite = unittest.TestSuite([BitwiseOpsScheduling_TC('test_2not1and_400MHz'), ])
    suite = testLoader.loadTestsFromTestCase(BitwiseOpsScheduling_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
