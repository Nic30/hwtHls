#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.serializer.combLoopAnalyzer import CombLoopAnalyzer
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.examples.errors.combLoops import freeze_set_of_sets
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.ast.writeTrue import WhileTrueWriteCntr0, WhileTrueWriteCntr1


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
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK = 5
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.dataOut._ag.data, ref)

    def test_WhileTrueWriteCntr1(self):
        self.test_WhileTrueWriteCntr0(cls=WhileTrueWriteCntr1, ref=[1, 2, 3, 4])


if __name__ == "__main__":
    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(HlsAstWhileTrue_TC('test_WhileTrueWrite'))
    suite.addTest(unittest.makeSuite(HlsAstWhileTrue_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
