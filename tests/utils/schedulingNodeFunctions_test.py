#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.types.defs import BIT
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwtHls.platform.virtual import VirtualHlsPlatform


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

        w._setScheduleZeroTimeSingleClock(clkPeriod - epsilon)  # at the end of clock window
        r._setScheduleZeroTimeSingleClock(epsilon)
        full = w.getFullPort()

        self.assertEqual(w.scheduledOut[full.out_i], 0 + epsilon)

        w._removeOutput(full.out_i)
        w._setScheduleZeroTimeSingleClock(clkPeriod)  # begin of clk 1
        full = w.getFullPort()
        self.assertEqual(w.scheduledOut[full.out_i], clkPeriod + epsilon)

        w._removeOutput(full.out_i)
        w._setScheduleZeroTimeSingleClock(clkPeriod + clkPeriod // 2)  # half of of clk 1
        full = w.getFullPort()
        self.assertEqual(w.scheduledOut[full.out_i], clkPeriod + epsilon)

        w._removeOutput(full.out_i)
        w._setScheduleZeroTimeSingleClock(2 * clkPeriod)
        full = w.getFullPort()
        self.assertEqual(w.scheduledOut[full.out_i], 2 * clkPeriod + epsilon)

    def test_HlsNetNodeAggregate_time_afterPortAdd(self):
        netlist = HlsNetlistCtx(None, int(100e6), "test", platform=VirtualHlsPlatform())
        clkPeriod = netlist.normalizedClkPeriod
        self.assertEqual(clkPeriod, 1001)
        epsilon = netlist.scheduler.epsilon
        self.assertEqual(epsilon, 1)

        r = HlsNetNodeRead(netlist, None, BIT)
        r.resolveRealization()
        r._setScheduleZeroTimeSingleClock(881)
        self.assertEqual(r.scheduledOut[0], 881)

        a = HlsNetNodeAggregate(netlist, SetList([r, ]), "agg0")
        a.assignRealization(EMPTY_OP_REALIZATION)

        a._setScheduleZeroTimeSingleClock(161)

        a._addOutput(BIT, "r_data", time=881)
        self.assertEqual(a.scheduledOut[0], 881)
        self.assertEqual(a._outputsInside[0].scheduledIn[0], 881)
        
        a._addInput(BIT, "aggI0", 1882)
        self.assertEqual(a.scheduledIn[0], 1882)
        self.assertEqual(a._inputsInside[0].scheduledOut[0], 1882)
        


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SchedulingNodeFunctions_TC('test_2not1and_400MHz'), ])
    suite = testLoader.loadTestsFromTestCase(SchedulingNodeFunctions_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
