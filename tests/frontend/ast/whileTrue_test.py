#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.serializer.combLoopAnalyzer import CombLoopAnalyzer
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtLib.examples.errors.combLoops import freeze_set_of_sets
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.utils import freq_to_period
from tests.frontend.ast.whileTrue import WhileTrueWriteCntr0, WhileTrueWriteCntr1, \
    WhileSendSequence0, WhileSendSequence1, WhileSendSequence2, WhileSendSequence3, \
    WhileSendSequence4
from hwtHls.platform.platform import HlsDebugBundle


class HlsAstWhileTrue_TC(SimTestCase):

    def _test_no_comb_loops(self):
        s = CombLoopAnalyzer()
        s.visit_Unit(self.u)
        comb_loops = freeze_set_of_sets(s.report())
        msg_buff = []
        for loop in comb_loops:
            msg_buff.append(10 * "-")
            for s in loop:
                msg_buff.append(str(s.resolve()[1:]))

        self.assertEqual(comb_loops, frozenset(), msg="\n".join(msg_buff))

    def test_WhileTrueWriteCntr0(self, cls=WhileTrueWriteCntr0, ref=[0, 1, 2, 3]):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform(debugFilter={*HlsDebugBundle.ALL_RELIABLE, HlsDebugBundle.DBG_20_addSyncSigNames}))
        CLK = 5
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.dataOut._ag.data, ref)

    def test_WhileTrueWriteCntr1(self):
        self.test_WhileTrueWriteCntr0(cls=WhileTrueWriteCntr1, ref=[1, 2, 3, 4])

    def _test_WhileSendSequence(self, cls: WhileSendSequence0, FREQ:int,
                                randomizeIn: bool, randomizeOut: bool,
                                platform=None,
                                timeMultiplier=1):
        u = cls()
        u.FREQ = int(FREQ)
        if platform is None:
            platform = VirtualHlsPlatform()
        self.compileSimAndStart(u, target_platform=platform)
        # u.dataIn._ag.data.extend([1, 1, 1, 1])

        u.dataIn._ag.data.extend([5, 0, 0, 3, 2, 0, 1, 3, 1,
                                  1, 0, 1])
        u.dataIn._ag.presetBeforeClk = True
        # u.dataIn._ag.data.extend([2, 2])
        CLK = 40
        if randomizeIn and randomizeOut:
            CLK *= 4
        elif randomizeIn or randomizeOut:
            CLK *= 3

        self.runSim(int(CLK * freq_to_period(u.FREQ) * timeMultiplier))
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.dataOut._ag.data, [5, 4, 3, 2, 1,
                                                         3, 2, 1,
                                                         2, 1,
                                                         1,
                                                         3, 2, 1,
                                                         1, 1, 1])

    def test_WhileSendSequence0_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence0, 20e6, False, False)

    def test_WhileSendSequence0_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence0, 100e6, False, False, timeMultiplier=2)

    def test_WhileSendSequence0_150Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence0, 150e6, False, False, timeMultiplier=2.5)

    # @expectedFailure  # problem with flush
    def test_WhileSendSequence1_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence1, 20e6, False, False)

    def test_WhileSendSequence1_40Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence1, 40e6, False, False)

    def test_WhileSendSequence1_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence1, 100e6, False, False)

    def test_WhileSendSequence1_150Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence1, 150e6, False, False)

    def test_WhileSendSequence2_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence2, 20e6, False, False)

    def test_WhileSendSequence2_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence2, 100e6, False, False, platform=Artix7Medium())

    def test_WhileSendSequence2_130Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence2, 130e6, False, False, platform=Artix7Medium())

    def test_WhileSendSequence3_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence3, 20e6, False, False)

    def test_WhileSendSequence3_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence3, 100e6, False, False, timeMultiplier=1.2)

    def test_WhileSendSequence3_150Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence3, 150e6, False, False, timeMultiplier=1.6)

    def test_WhileSendSequence4_20Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence4, 20e6, False, False)

    def test_WhileSendSequence4_100Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence4, 100e6, False, False, timeMultiplier=1.2)

    def test_WhileSendSequence4_150Mhz(self):
        self._test_WhileSendSequence(WhileSendSequence4, 150e6, False, False, timeMultiplier=1.6)

    def test_WhileSendSequence0_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence0, 20e6, True, True)

    def test_WhileSendSequence0_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence0, 100e6, True, True)

    def test_WhileSendSequence0_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence0, 150e6, True, True)

    # @expectedFailure  # problem with flush
    def test_WhileSendSequence1_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence1, 20e6, True, True)

    def test_WhileSendSequence1_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence1, 100e6, True, True)

    def test_WhileSendSequence1_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence1, 150e6, True, True)

    def test_WhileSendSequence2_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence2, 20e6, True, True)

    def test_WhileSendSequence2_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence2, 100e6, True, True)

    def test_WhileSendSequence2_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence2, 150e6, True, True)

    def test_WhileSendSequence3_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence3, 20e6, True, True)

    def test_WhileSendSequence3_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence3, 100e6, True, True)

    def test_WhileSendSequence3_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence3, 150e6, True, True)

    def test_WhileSendSequence4_20Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence4, 20e6, True, True)

    def test_WhileSendSequence4_100Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence4, 100e6, True, True)

    def test_WhileSendSequence4_150Mhz_rand(self):
        self._test_WhileSendSequence(WhileSendSequence4, 150e6, True, True)


if __name__ == "__main__":
    #from hwt.synthesizer.utils import to_rtl_str
    #u = WhileSendSequence1()
    #u.FREQ = int(20e6)
    #print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter={*HlsDebugBundle.ALL_RELIABLE, HlsDebugBundle.DBG_20_addSyncSigNames})))

    import unittest
    testLoader = unittest.TestLoader()
    #suite = unittest.TestSuite([HlsAstWhileTrue_TC('test_WhileSendSequence3_100Mhz')])
    suite = testLoader.loadTestsFromTestCase(HlsAstWhileTrue_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
