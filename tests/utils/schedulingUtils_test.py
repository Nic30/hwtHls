import unittest

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.scheduler.clk_math import clkWindowIndex, \
    clkWindowOffsetFromWindowBegin, clkWindowOffsetFromWindowEnd, \
    clkWindowBeginForTime, clkWindowBegin, clkWindowEnd, SchedTime
from hwtHls.netlist.techmap.techmap import clkWindowIndex as clkWindowIndexCpp, \
    clkWindowOffsetFromWindowBegin as clkWindowOffsetFromWindowBeginCpp \

from hwtHls.platform.virtual import VirtualHlsPlatform
from tests.hlsNetlist.abstractHlsNetlistTC import AbstractHlsNetlistTC
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.nodes.node import HlsNetNode


class SchedulingUtils_TC(AbstractHlsNetlistTC):

    def test(self):
        clkPeriod = 100

        for (t, ref) in ((0, 0),
                         (1, 0), (2, 0), (99, 0), (100, 1), (101, 1), (305, 3),
                         (-1, -1), (-2, -1), (-99, -1), (-100, -1), (-101, -2),
                         ):
            self.assertEqual(clkWindowIndex(t, clkPeriod), ref, t)
            self.assertEqual(clkWindowIndexCpp(t, clkPeriod), ref, t)

        for (t, ref) in ((0, 0),
                         (1, 1), (99, 99), (100, 0), (1001, 1),
                         (-1, 99), (-2, 98), (-100, 0), (-200, 0), (-203, 97),
                         ):
            self.assertEqual(clkWindowOffsetFromWindowBegin(t, clkPeriod), ref, t)
            self.assertEqual(clkWindowOffsetFromWindowBeginCpp(t, clkPeriod), ref, t)

        for (t, ref) in (
            (0, 100),
            (1, 99), (2, 98), (99, 1), (100, 100), (199, 1), (205, 95),
            (-1, 1), (-2, 2), (-100, 100), (-101, 1), (-405, 5),
            ):
            self.assertEqual(clkWindowOffsetFromWindowEnd(t, clkPeriod), ref, t)
            # self.assertEqual(clkWindowOffsetFromWindowEndCpp(t, clkPeriod), ref, t)

        for (t, ref) in (
            (0, 0), (1, 0), (2, 0), (100, 100), (101, 100), (199, 100),
            (-1, -100), (-2, -100), (-100, -100), (-101, -200), (-199, -200),
            ):
            self.assertEqual(clkWindowBeginForTime(t, clkPeriod), ref, t)

        for (t, ref) in (
            (0, 0), (1, 100), (-1, -100)
            ):
            self.assertEqual(clkWindowBegin(t, clkPeriod), ref, t)

        for (t, ref) in ((0, 99),
                          (1, 199),
                          (2, 299),
                          (-1, -1), (-2, -101), (-3, -201),
                          ):
            self.assertEqual(clkWindowEnd(t, clkPeriod), ref, t)

        # def clkWindowBeginOfNext(time: int, clkPeriod: int):
        #
    def _test_alapCompaction_forNot(self, inWireDelay: SchedTime, outWireDelay: SchedTime):
        assert inWireDelay + outWireDelay == 100
        netlist = self.getTestNetlist(freq=int(100e6))
        b = netlist.getHlsNetlistBuilder()

        i0, = self.generateTestNetlistInputsFromCnt(netlist, 1, BIT)
        _o0 = b.buildNot(i0)

        o0, = self.generateTestNetlistOutputs(netlist, [_o0, ])
        clkPeriod = netlist.normalizedClkPeriod = 1000
        epsilon = netlist.scheduler.epsilon

        def get_ff_store_time(rtClk, resolution):
            return 100

        netlist.platform.get_ff_store_time = get_ff_store_time
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)

        # node stays where it is
        for o in (i0, _o0):
            o.obj.resolveRealization()
        o0.resolveRealization()
        n: HlsNetNode = _o0.obj
        i0.obj._setScheduleZeroTimeSingleClock(10)
        n.inputWireDelay = (inWireDelay,)
        n.outputWireDelay = (outWireDelay,)
        endOfLastClk = 10000

        n._setScheduleZeroTimeSingleClock(10)
        o0._setScheduleZeroTimeSingleClock(110)

        for _ in n.scheduleAlapCompaction(endOfLastClk, None, None):
            pass

        self.assertEqual(n.scheduledZero, 110 - outWireDelay)

        # node moves in the same clk
        # n._setScheduleZeroTimeSingleClock(10)
        o0._setScheduleZeroTimeSingleClock(120)

        for _ in n.scheduleAlapCompaction(endOfLastClk, None, None):
            pass

        self.assertEqual(n.scheduledZero, 120 - outWireDelay)

        # node snaps to clk end where it is because is not enough time of node in next clk window
        o0._setScheduleZeroTimeSingleClock(clkPeriod)
        for _ in n.scheduleAlapCompaction(endOfLastClk, None, None):
            pass

        self.assertEqual(n.scheduledZero, clkPeriod - ffdelay - outWireDelay)

        o0._setScheduleZeroTimeSingleClock(clkPeriod + 100 - 1)
        for _ in n.scheduleAlapCompaction(endOfLastClk, None, None):
            pass

        self.assertEqual(n.scheduledZero, clkPeriod - ffdelay - outWireDelay)

        # node moves to next clk
        o0._setScheduleZeroTimeSingleClock(clkPeriod + 100 + 1)
        for _ in n.scheduleAlapCompaction(endOfLastClk, None, None):
            pass

        self.assertEqual(n.scheduledZero, clkPeriod + inWireDelay + 1)

        # node moves to next clk but not next-next clk where there is not enough time
        o0._setScheduleZeroTimeSingleClock(2 * clkPeriod + 100 - 1)
        for _ in n.scheduleAlapCompaction(endOfLastClk, None, None):
            pass

        self.assertEqual(n.scheduledZero, 2 * clkPeriod - ffdelay - outWireDelay)

    def test_alapCompaction_inDelayOnly(self):
        self._test_alapCompaction_forNot(100, 0)

    def test_alapCompaction_inOutDelay(self):
        self._test_alapCompaction_forNot(50, 50)

    def test_alapCompaction_outDelayOnly(self):
        self._test_alapCompaction_forNot(0, 100)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SchedulingNodeFunctions_TC('test_2not1and_400MHz'), ])
    suite = testLoader.loadTestsFromTestCase(SchedulingUtils_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
