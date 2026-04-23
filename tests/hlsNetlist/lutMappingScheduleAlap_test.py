#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.types.defs import BIT
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.techmap.hlsNetlistToCppTranslator import HlsNetlistToCppTranslator
from hwtHls.netlist.techmap.techmap import FlowmapWorker, HlsNetNode as HlsNetNodeCpp, \
    scheduleLutAlap
from tests.hlsNetlist.abstractHlsNetlistTC import AbstractHlsNetlistTC
from tests.hlsNetlist.lutMapping_test import LutMappingTC


class LutMappingScehdulingAlapTC(AbstractHlsNetlistTC):

    def runFlowmapWorker(self, nodes: SetList[HlsNetNode], normalizedClkPeriod: SchedTime=100 , maxLutInputs=3) \
            ->tuple[HlsNetlistToCppTranslator, FlowmapWorker, dict[HlsNetNodeCpp, HlsNetNode]]:
        return LutMappingTC.runFlowmapWorker(self, nodes, normalizedClkPeriod, maxLutInputs)

    def printLuts(self, fmw, cppToPy):
        return LutMappingTC.printLuts(self, fmw, cppToPy)

    def test_1layer_1clk_1node(self):
        netlist = self.getTestNetlist()
        b = netlist.getHlsNetlistBuilder()

        i0, i1 = self.generateTestNetlistInputsFromCnt(netlist, 2, BIT)
        _o0 = b.buildAnd(i0, i1)
        o0, = self.generateTestNetlistOutputs(netlist, [_o0, ])
        o0.resolveRealization()
        o0._setScheduleZeroTimeSingleClock(80)
        tr, fmw, cppToPy = self.runFlowmapWorker(SetList(netlist.subNodes))

        # i0r, i1r = [tr.nodeMap[i.obj] for i in [i0, i1]]
        # i0r: HlsNetNodeRead
        # i1r: HlsNetNodeRead
        # i0r._setScheduleZeroTimeSingleClock(10)
        # i1r._setScheduleZeroTimeSingleClock(20)
        lutDelay = 50
        endOfLastClk = 100
        scheduleLutAlap(fmw, lutDelay, endOfLastClk)
        schedule = {n._id: n.scheduledZero for n in tr.nodeMap.values()}
        #lutBegin = 80 - lutDelay
        self.assertDictEqual(schedule, {0: 30, 1: 30, 2: 80, 3: 80})
        # self.printLuts(fmw, cppToPy)

    def test_2layer_1clk_2node(self):
        netlist = self.getTestNetlist()
        b = netlist.getHlsNetlistBuilder()

        i0, i1, i2, i3 = self.generateTestNetlistInputsFromCnt(netlist, 4, BIT)
        _o0 = b.buildAnd(i0, i1)
        lut0 = b.buildAnd(_o0, i2)
        lut1 = b.buildAnd(lut0, i3)
        
        o0, = self.generateTestNetlistOutputs(netlist, [lut1, ])
        o0.resolveRealization()
        o0._setScheduleZeroTimeSingleClock(80)
        tr, fmw, cppToPy = self.runFlowmapWorker(SetList(netlist.subNodes))

        lutDelay = 20
        endOfLastClk = 100
        scheduleLutAlap(fmw, lutDelay, endOfLastClk)
        schedule = {n._id: n.scheduledZero for n in tr.nodeMap.values()}
        self.assertDictEqual(schedule, {0: 40, 1: 40, 2: 40, 3: 60, 4: 60, 5: 60, 6: 80, 7: 80})
        # self.printLuts(fmw, cppToPy)

if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(LutMappingScehdulingAlapTC)
    # suite = unittest.TestSuite([LutMappingScehdulingAlapTC("test_4Lut_8inputAndTree_2outputs")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
