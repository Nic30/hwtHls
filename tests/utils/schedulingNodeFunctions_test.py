#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.types.defs import BIT
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge,\
    HlsNetNodeReadBackedge


class SchedulingNodeFunctions_TC(unittest.TestCase):

    def test_delay(self):
        netlist = HlsNetlistCtx(None, int(1e6), "test", platform=VirtualHlsPlatform())
        clkPeriod = netlist.normalizedClkPeriod
        epsilon = netlist.scheduler.epsilon
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)

        n = HlsNetNodeDelayClkTick(netlist, 1, BIT)
        n.resolveRealization()

        n._setScheduleZeroTimeMultiClock(0, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], 0)
        self.assertEqual(n.scheduledOut[0], clkPeriod)

        n._setScheduleZeroTimeMultiClock(1, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], 1)
        self.assertEqual(n.scheduledOut[0], clkPeriod)

        n._setScheduleZeroTimeMultiClock(clkPeriod - 1, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], clkPeriod - 1)
        self.assertEqual(n.scheduledOut[0], clkPeriod)

        n._setScheduleZeroTimeMultiClock(clkPeriod, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], clkPeriod)
        self.assertEqual(n.scheduledOut[0], clkPeriod * 2)

        n._setScheduleZeroTimeMultiClock(clkPeriod + 1, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], clkPeriod + 1)
        self.assertEqual(n.scheduledOut[0], clkPeriod * 2)

        n = HlsNetNodeDelayClkTick(netlist, 2, BIT)
        n.resolveRealization()

        n._setScheduleZeroTimeMultiClock(0, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], 0)
        self.assertEqual(n.scheduledOut[0], clkPeriod * 2)

        n._setScheduleZeroTimeMultiClock(1, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], 1)
        self.assertEqual(n.scheduledOut[0], clkPeriod * 2)

        n._setScheduleZeroTimeMultiClock(clkPeriod - 1, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], clkPeriod - 1)
        self.assertEqual(n.scheduledOut[0], clkPeriod * 2)

        n._setScheduleZeroTimeMultiClock(clkPeriod, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], clkPeriod)
        self.assertEqual(n.scheduledOut[0], clkPeriod * 3)

        n._setScheduleZeroTimeMultiClock(clkPeriod + 1, clkPeriod, epsilon, ffdelay)
        self.assertEqual(n.scheduledIn[0], clkPeriod + 1)
        self.assertEqual(n.scheduledOut[0], clkPeriod * 3)

    def test_HlsNetNodeWriteBackedge_full(self):
        netlist = HlsNetlistCtx(None, int(1e6), "test", platform=VirtualHlsPlatform())
        clkPeriod = netlist.normalizedClkPeriod
        epsilon = netlist.scheduler.epsilon

        w = HlsNetNodeWriteBackedge(netlist)
        r = HlsNetNodeReadBackedge(netlist, BIT)

        w.resolveRealization()
        w.associateRead(r)
        r.resolveRealization()

        w._setScheduleZeroTimeSingleClock(clkPeriod - epsilon) # at the end of clock window
        r._setScheduleZeroTimeSingleClock(epsilon)
        full = w.getFullPort()

        self.assertEqual(w.scheduledOut[full.out_i], 0 + epsilon)
        
        w._removeOutput(full.out_i)
        w._setScheduleZeroTimeSingleClock(clkPeriod) # begin of clk 1
        full = w.getFullPort()
        self.assertEqual(w.scheduledOut[full.out_i], clkPeriod + epsilon)
        
        w._removeOutput(full.out_i)
        w._setScheduleZeroTimeSingleClock(clkPeriod + clkPeriod//2) # half of of clk 1
        full = w.getFullPort()
        self.assertEqual(w.scheduledOut[full.out_i], clkPeriod + epsilon)

        w._removeOutput(full.out_i)
        w._setScheduleZeroTimeSingleClock(2*clkPeriod)
        full = w.getFullPort()
        self.assertEqual(w.scheduledOut[full.out_i], 2*clkPeriod + epsilon)
                

if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SchedulingNodeFunctions_TC('test_2not1and_400MHz'), ])
    suite = testLoader.loadTestsFromTestCase(SchedulingNodeFunctions_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
