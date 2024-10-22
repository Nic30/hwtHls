#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from io import StringIO
import os
import sys
import unittest

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwtHls.architecture.transformation.addImplicitSyncChannels import HlsArchPassAddImplicitSyncChannels
from hwtHls.architecture.transformation.syncLowering import HlsArchPassSyncLowering
from hwtHls.architecture.transformation.syncPredicatePruning import HlsArchPassSyncPredicatePruning
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUncheduledDummyAlap
from hwtHls.architecture.translation.dumpHsSCCsDot import RtlArchAnalysisPassDumpHsSCCsDot
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.ports import _getPortDrive
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.archElementStageInit import HlsNetlistPassArchElementStageInit
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistAnalysisPassDumpNodesDot
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.examples.base_serialization_TC import BaseSerializationTC


class RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC(BaseSerializationTC):
    __FILE__ = __file__

    @staticmethod
    def _createNetlistWithPipe():
        netlist = HlsNetlistCtx(None, int(100e6), "test", {}, platform=VirtualHlsPlatform())
        pipeElm = ArchElementPipeline(netlist, "p0", "p0_")
        pipeElm.resolveRealization()
        pipeElm._setScheduleZeroTimeSingleClock(0)
        netlist.addNode(pipeElm)
        return netlist, pipeElm

    def _assertNetlistMatchesRefFile(self, netlist: HlsNetlistCtx, runPredicatePruning=True, debugDumpEnable=False):
        if debugDumpEnable:
            netlist._dbgLogPassExec = sys.stderr
        HlsNetlistPassArchElementStageInit().runOnHlsNetlist(netlist)
        if runPredicatePruning:
            HlsArchPassSyncPredicatePruning().runOnHlsNetlist(netlist)
        HlsArchPassAddImplicitSyncChannels().runOnHlsNetlist(netlist)
        if debugDumpEnable:
            os.makedirs("tmp/test", exist_ok=True)
            RtlArchAnalysisPassDumpHsSCCsDot(lambda name: (open(f"tmp/test/hsscc.{name}.dot", "w"), True)).runOnHlsNetlist(netlist)
        try:
            HlsArchPassSyncLowering(dbgDumpAbc=debugDumpEnable, dbgDumpNodes=debugDumpEnable).runOnHlsNetlist(netlist)
        except:
            if debugDumpEnable:
                HlsNetlistAnalysisPassDumpNodesDot(lambda name: (open(f"tmp/test/netlistErr.{name}.dot", "w"), True),
                                                    expandAggregates=True, addLegend=False, addOrderingNodes=False
                                                    ).runOnHlsNetlist(netlist)

            raise
        buff = StringIO()
        HlsNetlistAnalysisPassDumpNodesDot(lambda name: (buff, False),
                                           expandAggregates=True, addLegend=False, addOrderingNodes=False
                                           ).runOnHlsNetlist(netlist)
        self.assert_same_as_file(buff.getvalue(), "data/" + self.getTestName() + ".dot")

    def _constructLinear1Read1Write(self, netlist, elm):
        # r0 = read()
        # w.write(r0)
        b: HlsNetlistBuilder = elm.builder

        r0 = HlsNetNodeRead(netlist, None, dtype=HBits(8))
        elm.addNode(r0)
        w = HlsNetNodeWrite(netlist, None)
        elm.addNode(w)
        r0._portDataOut.connectHlsIn(w._portSrc)
        w_en = r0.getValidNB()
        w_en_n = b.buildNot(w_en, "w_en_n")
        w.addControlSerialExtraCond(w_en)
        w.addControlSerialSkipWhen(w_en_n)
        return r0, w

    def _constructLinear1Read1WriteWithNe0(self, netlist: HlsNetlistCtx, elm: ArchElement):
        # r0 = read()
        # if r0 != 0:
        #   w.write(r0)
        b: HlsNetlistBuilder = elm.builder
        r0 = HlsNetNodeRead(netlist, None, dtype=HBits(8))
        elm.addNode(r0)
        w = HlsNetNodeWrite(netlist, None)
        elm.addNode(w)
        r0._portDataOut.connectHlsIn(w._portSrc)
        r0_ne0 = b.buildNe(r0._portDataOut, r0._portDataOut._dtype.from_py(0))
        w_en = b.buildAnd(r0_ne0, r0.getValidNB(), "w_en")
        w_en_n = b.buildNot(w_en, "w_en_n")
        w.addControlSerialExtraCond(w_en)
        w.addControlSerialSkipWhen(w_en_n)
        return r0, w

    def _constructLinear1Read1WriteWithEnRead(self, netlist: HlsNetlistCtx, elm: ArchElement):
        # r0 = read()
        # r1 = read()
        # if r1:
        #   w.write(r0)
        b: HlsNetlistBuilder = elm.builder
        r0 = HlsNetNodeRead(netlist, None, dtype=HBits(8))
        elm.addNode(r0)
        r1 = HlsNetNodeRead(netlist, None, dtype=BIT)
        elm.addNode(r1)
        w = HlsNetNodeWrite(netlist, None)
        elm.addNode(w)
        r0._portDataOut.connectHlsIn(w._portSrc)
        r1_v = b.buildAnd(r1._portDataOut, r1.getValidNB())
        w_en = b.buildAnd(r1_v, r0.getValidNB(), "w_en")
        w_en_n = b.buildNot(w_en, "w_en_n")
        w.addControlSerialExtraCond(w_en)
        w.addControlSerialSkipWhen(w_en_n)
        return r0, r1, w

    def _constructLinear1Read2WriteWithEnRead(self, netlist: HlsNetlistCtx, elm: ArchElement):
        # r0 = read()
        # r1 = read()
        # if r1:
        #   w0.write(r0)
        #   w1.write(r0)
        r0, r1, w0 = self._constructLinear1Read1WriteWithEnRead(netlist, elm)
        b: HlsNetlistBuilder = elm.builder
        w1 = HlsNetNodeWrite(netlist, None)
        elm.addNode(w1)
        r0._portDataOut.connectHlsIn(w1._portSrc)
        w1.addControlSerialExtraCond(_getPortDrive(w0.extraCond))
        w1.addControlSerialSkipWhen(_getPortDrive(w0.skipWhen))
        return r0, r1, w0, w1

    def _constructLinear1Read2WriteWithNe0(self, netlist: HlsNetlistCtx, elm: ArchElement):
        # r0 = read()
        # if r0 != 0:
        #   w0.write(r0)
        #   w1.write(r0)
        r0, r1, w0 = self._constructLinear1Read1WriteWithNe0(netlist, elm)
        b: HlsNetlistBuilder = elm.builder
        w1 = HlsNetNodeWrite(netlist, None)
        elm.addNode(w1)
        r0._portDataOut.connectHlsIn(w1._portSrc)
        w1.addControlSerialExtraCond(_getPortDrive(w0.extraCond))
        w1.addControlSerialSkipWhen(_getPortDrive(w0.skipWhen))
        return r0, r1, w0, w1

    def test_linear1Clk(self, logicClkIndex=0, wClkI=0, runPredicatePruning=True):
        # r0 = read()
        # w.write(r0)
        netlist, elm = self._createNetlistWithPipe()
        netlist: HlsNetlistCtx
        elm: ArchElementPipeline

        r0, w = self._constructLinear1Read1Write(netlist, elm)

        clkPeriod = netlist.normalizedClkPeriod

        r0.resolveRealization()
        r0._setScheduleZeroTimeSingleClock(0)
        for dep in w.dependsOn:
            scheduleUncheduledDummyAlap(dep, logicClkIndex * clkPeriod + 10, allowNewClockWindow=True)
        w.resolveRealization()
        w._setScheduleZeroTimeSingleClock(wClkI * clkPeriod + 15)

        self._assertNetlistMatchesRefFile(netlist, runPredicatePruning=runPredicatePruning)

    def test_linear2Clk(self, runPredicatePruning=True):
        # r0 = read()
        # # clk 1
        # w.write(r0)
        self.test_linear1Clk(wClkI=1, runPredicatePruning=runPredicatePruning)

    def test_linearWithNe0_1Clk(self, logicClkIndex=0, wClkIndex=0):
        # r0 = read()
        # if r0 != 0:
        #   w.write(r0)
        netlist, elm = self._createNetlistWithPipe()
        netlist: HlsNetlistCtx
        elm: ArchElementPipeline

        r0, w = self._constructLinear1Read1WriteWithNe0(netlist, elm)
        clkPeriod = netlist.normalizedClkPeriod
        r0.resolveRealization()
        r0._setScheduleZeroTimeSingleClock(0)
        for dep in w.dependsOn:
            scheduleUncheduledDummyAlap(dep, logicClkIndex * clkPeriod + 10, allowNewClockWindow=True)
        w.resolveRealization()
        w._setScheduleZeroTimeSingleClock(wClkIndex * clkPeriod + 15)

        self._assertNetlistMatchesRefFile(netlist)

    def test_linearWithNe0_2Clk_a(self):
        # r0 = read()
        # if r0 != 0:
        #   # clk 1
        #   w.write(r0)
        self.test_linearWithNe0_1Clk(logicClkIndex=0, wClkIndex=1)

    def test_linearWithNe0_2Clk_b(self):
        # r0 = read()
        # # clk 1
        # if r0 != 0:
        #   w.write(r0)
        self.test_linearWithNe0_1Clk(logicClkIndex=1, wClkIndex=1)

    def test_linear2Clk_noPredicatePruning(self):
        self.test_linear2Clk(runPredicatePruning=False)

    def test_linearWithEn1Clk(self, logicClkI=0, wClkI=0, runPredicatePruning=True):
        # r0 = read()
        # r1 = read()
        # if r1:
        #   w.write(r0)
        netlist, elm = self._createNetlistWithPipe()
        netlist: HlsNetlistCtx
        elm: ArchElementPipeline

        r0, r1, w = self._constructLinear1Read1WriteWithEnRead(netlist, elm)

        for r in (r0, r1):
            r.resolveRealization()
            r._setScheduleZeroTimeSingleClock(0)

        clkPeriod = netlist.normalizedClkPeriod
        for dep in w.dependsOn:
            scheduleUncheduledDummyAlap(dep, logicClkI * clkPeriod + 10, allowNewClockWindow=True)

        w.resolveRealization()
        w._setScheduleZeroTimeSingleClock(clkPeriod * wClkI + 15)

        self._assertNetlistMatchesRefFile(netlist, runPredicatePruning=runPredicatePruning)

    def test_linearWithEn1Clk_noPredicatePruning(self):
        self.test_linearWithEn1Clk(runPredicatePruning=False)

    def test_linearWithEn2Clk_logicInClk0(self, runPredicatePruning=True):
        # r0 = read()
        # r1 = read()
        # if r1:
        #   # clk 1
        #   w.write(r0)
        self.test_linearWithEn1Clk(logicClkI=0, wClkI=1, runPredicatePruning=runPredicatePruning)

    def test_linearWithEn2Clk_logicInClk0_noPredicatePruning(self):
        self.test_linearWithEn2Clk_logicInClk0(runPredicatePruning=False)

    def test_linearWithEn2Clk_logicInClk1(self, runPredicatePruning=True):
        # r0 = read()
        # r1 = read()
        # # clk 1
        # if r1:
        #   w.write(r0)
        self.test_linearWithEn1Clk(logicClkI=1, wClkI=1, runPredicatePruning=runPredicatePruning)

    def test_linearWithEn2Clk_logicInClk1_noPredicatePruning(self):
        self.test_linearWithEn2Clk_logicInClk1(runPredicatePruning=False)

    def test_linearWithEn2Clk_logicInClk1_wInClk2(self, runPredicatePruning=True):
        # r0 = read()
        # r1 = read()
        # # clk 1
        # if r1:
        #   # clk 2
        #   w.write(r0)
        self.test_linearWithEn1Clk(logicClkI=1, wClkI=2, runPredicatePruning=runPredicatePruning)

    def test_linearWithEn2Clk_logicInClk2_noPredicatePruning(self):
        self.test_linearWithEn2Clk_logicInClk1_wInClk2(runPredicatePruning=False)

    def test_linear2xWriteWithEn(self, logicClkI=0, w0ClkI=0, w1ClkI=0, runPredicatePruning=True):
        # r0 = read()
        # r1 = read()
        # if r1:
        #   w0.write(r0)
        #   w1.write(r0)
        netlist, elm = self._createNetlistWithPipe()
        netlist: HlsNetlistCtx
        elm: ArchElementPipeline

        r0, r1, w0, w1 = self._constructLinear1Read2WriteWithEnRead(netlist, elm)

        for r in (r0, r1):
            r.resolveRealization()
            r._setScheduleZeroTimeSingleClock(0)

        clkPeriod = netlist.normalizedClkPeriod

        for w, wClkI in ((w0, w0ClkI), (w1, w1ClkI)):
            for dep in w.dependsOn:
                scheduleUncheduledDummyAlap(dep, logicClkI * clkPeriod + 10, allowNewClockWindow=True)

            w.resolveRealization()
            w._setScheduleZeroTimeSingleClock(clkPeriod * wClkI + 15)

        self._assertNetlistMatchesRefFile(netlist, runPredicatePruning=runPredicatePruning)

    def test_linear2xWriteWithEn_noPredicatePruning(self):
        self.test_linear2xWriteWithEn(runPredicatePruning=False)

    def test_linear2xWriteWithEn_w0InClk1_w1InClk1(self, runPredicatePruning=True):
        # r0 = read()
        # r1 = read()
        # if r1:
        #   # clk 1
        #   w0.write(r0)
        #   w1.write(r0)
        self.test_linear2xWriteWithEn(logicClkI=0, w0ClkI=1, w1ClkI=1, runPredicatePruning=runPredicatePruning)

    def test_linear2xWriteWithEn_w0InClk1_w1InClk1_noPredicatePruning(self):
        self.test_linear2xWriteWithEn_w0InClk1_w1InClk1(runPredicatePruning=True)

    def test_linear2xWriteWithEn_w0InClk1_w1InClk2(self, runPredicatePruning=True):
        # r0 = read()
        # r1 = read()
        # if r1:
        #   # clk 1
        #   w0.write(r0)
        #   # clk 2
        #   w1.write(r0)
        self.test_linear2xWriteWithEn(logicClkI=0, w0ClkI=1, w1ClkI=2, runPredicatePruning=runPredicatePruning)

    def test_linear2xWriteWithEn_w0InClk1_w1InClk2_noPredicatePruning(self):
        self.test_linear2xWriteWithEn_w0InClk1_w1InClk2(runPredicatePruning=True)

    def test_linear2xWriteWithEn_logicInClk1_w0InClk1_w1InClk2(self, runPredicatePruning=True):
        # r0 = read()
        # r1 = read()
        # clk 1
        # if r1:
        #   w0.write(r0)
        #   # clk 2
        #   w1.write(r0)
        self.test_linear2xWriteWithEn(logicClkI=1, w0ClkI=1, w1ClkI=2, runPredicatePruning=runPredicatePruning)

    def test_linear2xWriteWithEn_logicInClk1_w0InClk1_w1InClk2_noPredicatePruning(self):
        self.test_linear2xWriteWithEn_logicInClk1_w0InClk1_w1InClk2(runPredicatePruning=True)

    def test_linear2xWriteWithNe0(self, logicClkI=0, w0ClkI=0, w1ClkI=0, runPredicatePruning=True):
        # r0 = read()
        # if r0 != 0:
        #   w0.write(r0)
        #   w1.write(r0)
        netlist, elm = self._createNetlistWithPipe()
        netlist: HlsNetlistCtx
        elm: ArchElementPipeline

        r0, r1, w0, w1 = self._constructLinear1Read2WriteWithEnRead(netlist, elm)

        for r in (r0, r1):
            r.resolveRealization()
            r._setScheduleZeroTimeSingleClock(0)

        clkPeriod = netlist.normalizedClkPeriod

        for w, wClkI in ((w0, w0ClkI), (w1, w1ClkI)):
            for dep in w.dependsOn:
                scheduleUncheduledDummyAlap(dep, logicClkI * clkPeriod + 10, allowNewClockWindow=True)

            w.resolveRealization()
            w._setScheduleZeroTimeSingleClock(clkPeriod * wClkI + 15)

        self._assertNetlistMatchesRefFile(netlist, runPredicatePruning=runPredicatePruning)

    def test_linear2xWriteWithNe0_logicInClk1_w0InClk1_w1InClk2(self, runPredicatePruning=True):
        self.test_linear2xWriteWithNe0(logicClkI=1, w0ClkI=1, w1ClkI=2, runPredicatePruning=runPredicatePruning)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC("test_linearWithNe0_2Clk_b")])
    suite = testLoader.loadTestsFromTestCase(RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
