#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUncheduledDummyAlap
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtLib.examples.base_serialization_TC import BaseSerializationTC
from tests.hlsNetlist.syncLowering_exprExtraction_test import RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC


class RtlArchPassSyncLowering_exprExtraction_negations_TC(BaseSerializationTC):
    __FILE__ = __file__

    @staticmethod
    def _createNetlistWithPipe():
        return RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC._createNetlistWithPipe()

    def _assertNetlistMatchesRefFile(self, netlist: HlsNetlistCtx, runPredicatePruning=True, debugDumpEnable=False):
        RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC._assertNetlistMatchesRefFile(self, netlist, runPredicatePruning, debugDumpEnable)

#    def test_inSelOutSel(self, netlist: HlsNetlistCtx, elm: ArchElement):
#        # r0 = read()
#        # if r0 != 0:
#        #    r1 = read()
#        #    en = r1 != 1
#        # else:
#        #    r2 = read()
#        #    en = r2 != 2
#        #
#        # if en & (r1.validNB | r2.validNB):
#        #   w0.write(r1)
#        # else:
#        #   w1.write(r2)
#        netlist, elm = self._createNetlistWithPipe()
#        netlist: HlsNetlistCtx
#        elm: ArchElementPipeline
#
#
#        b: HlsNetlistBuilder = elm.builder
#        t = HBits(8)
#        r0 = HlsNetNodeRead(netlist, None, dtype=t)
#        r1 = HlsNetNodeRead(netlist, None, dtype=t)
#        r2 = HlsNetNodeRead(netlist, None, dtype=t)
#        w0 = HlsNetNodeWrite(netlist, None)
#        w1 = HlsNetNodeWrite(netlist, None)
#        for n in (r0, r1, r2, w0, w1):
#            elm.addNode(n)
#
#        r0_ne0 = b.buildNe(r0._portDataOut, t.from_py(0))
#        r0_ne0_n = b.buildNot(r0_ne0)
#
#        r1.addControlSerialExtraCond(r0_ne0)
#        r1.addControlSerialSkipWhen(r0_ne0_n)
#
#        r2.addControlSerialExtraCond(r0_ne0_n)
#        r2.addControlSerialSkipWhen(r0_ne0)
#
#        en0 = b.buildMux(BIT, (b.buildNe(r1._portSrc, t.from_py(1)),
#                              r0_ne0,
#                              b.buildNe(r2._portSrc, t.from_py(2)),
#                              ), "en0")
#
#        en1 = b.buildAnd(en0, b.buildOr(r1.getValidNB(), r2.getValidNB()), "en1")
#        en1_n = b.buildNot(en1, "en1_n")
#
#        r1._portDataOut.connectHlsIn(w0._portSrc)
#        w0.addControlSerialExtraCond(en1)
#        w0.addControlSerialSkipWhen(en1_n)
#
#        r2._portDataOut.connectHlsIn(w1._portSrc)
#        w1.addControlSerialExtraCond(en1_n)
#        w1.addControlSerialSkipWhen(en1)

    def test_inSelOutEn(self):
        # # clk 0
        # r0 = read()
        # if r0 != 0:
        #    r1 = read()
        # else:
        #    r2 = read()
        #
        # # clk 1
        # if r0 != 0:
        #    en0 = r1 != 1
        # else:
        #    en0 = r2 != 2
        # if en0:
        #   w0.write(r1)
        #
        # # clk 2
        # if en0 & (r0 != 10):
        #   w1.write(r2)
        netlist, elm = self._createNetlistWithPipe()
        netlist: HlsNetlistCtx
        elm: ArchElementPipeline

        b: HlsNetlistBuilder = elm.builder
        t = HBits(8)
        r0 = HlsNetNodeRead(netlist, None, dtype=t)
        r1 = HlsNetNodeRead(netlist, None, dtype=t)
        r2 = HlsNetNodeRead(netlist, None, dtype=t)
        w0 = HlsNetNodeWrite(netlist, None)
        w1 = HlsNetNodeWrite(netlist, None)
        for n in (r0, r1, r2, w0, w1):
            elm.addNode(n)

        # clk 0
        r0_ne0 = b.buildNe(r0._portDataOut, t.from_py(0))
        r0_ne0_n = b.buildNot(r0_ne0)

        r1.addControlSerialExtraCond(r0_ne0)
        r1.addControlSerialSkipWhen(r0_ne0_n)

        r2.addControlSerialExtraCond(r0_ne0_n)
        r2.addControlSerialSkipWhen(r0_ne0)

        # clk 1
        en0 = b.buildMux(BIT, (b.buildNe(r1._portDataOut, t.from_py(1)),
                              r0_ne0,
                              b.buildNe(r2._portDataOut, t.from_py(2)),
                              ), "en0")
        en0_n = b.buildNot(en0, "en0_n")
        r1._portDataOut.connectHlsIn(w0._portSrc)
        w0.addControlSerialExtraCond(en0)
        w0.addControlSerialSkipWhen(en0_n)

        # clk 2
        en1 = b.buildAnd(en0, b.buildNe(r0._portDataOut, t.from_py(10)), "en1")
        en1_n = b.buildNot(en1, "en1_n")

        r2._portDataOut.connectHlsIn(w1._portSrc)
        w1.addControlSerialExtraCond(en1)
        w1.addControlSerialSkipWhen(en1_n)

        clkPeriod = netlist.normalizedClkPeriod

        r0.resolveRealization()
        r0._setScheduleZeroTimeSingleClock(0)

        for r in (r1, r2):
            r.resolveRealization()
            r._setScheduleZeroTimeSingleClock(15)
            for dep in r.dependsOn:
                scheduleUncheduledDummyAlap(dep, 10, allowNewClockWindow=True)

        w0.resolveRealization()
        w0._setScheduleZeroTimeSingleClock(clkPeriod + 15)
        for dep in w0.dependsOn:
            scheduleUncheduledDummyAlap(dep, clkPeriod + 10, allowNewClockWindow=True)

        w1.resolveRealization()
        w1._setScheduleZeroTimeSingleClock(2 * clkPeriod + 15)
        for dep in w1.dependsOn:
            scheduleUncheduledDummyAlap(dep, 2 * clkPeriod + 10, allowNewClockWindow=True)

        self._assertNetlistMatchesRefFile(netlist, runPredicatePruning=True)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC("test_linear2Clk")])
    suite = testLoader.loadTestsFromTestCase(RtlArchPassSyncLowering_exprExtraction_negations_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
