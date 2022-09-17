#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.frontend.pyBytecode.preprocLoopMultiExit import PreprocLoopMultiExit_singleExit0, \
    PreprocLoopMultiExit_hwBreak0, PreprocLoopMultiExit_singleExit1


class PreprocLoopMultiExit_singleExit0_TC(SimTestCase):
    __FILE__ = __file__
    
    @classmethod
    def setUpClass(cls):
        u = cls.u = PreprocLoopMultiExit_singleExit0()
        # if read(i) != 0:
        #     write(0, o)
        # if read(i) != 1:
        #     write(1, o)
        # if read(i) != 2:
        #     write(2, o)
        cls.compileSim(u, target_platform=VirtualHlsPlatform())

    def _test(self, refInput: List[int], expectedOutput: List[int], CLK_CNT=10):
        u = self.u
        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        u.i._ag.data.extend(refInput)
        self.runSim(CLK_CNT * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.o._ag.data, expectedOutput)

    def test_withData(self):

        self._test([10, 1, 11], [0, 2])
               
    def test_noData(self):
        self._test([], [])


class PreprocLoopMultiExit_singleExit1_TC(PreprocLoopMultiExit_singleExit0_TC):

    @classmethod
    def setUpClass(cls):
        u = cls.u = PreprocLoopMultiExit_singleExit1()
        cls.compileSim(u, target_platform=VirtualHlsPlatform())


class PreprocLoopMultiExit_hwBreak0_TC(SimTestCase):
    __FILE__ = __file__
    
    @classmethod
    def setUpClass(cls):
        u = cls.u = PreprocLoopMultiExit_hwBreak0()
        cls.compileSim(u, target_platform=VirtualHlsPlatform())

    def _test(self, refInput: List[int], expectedOutput: List[int], CLK_CNT=10):
        PreprocLoopMultiExit_singleExit0_TC._test(self, refInput, expectedOutput, CLK_CNT)

    def test_noData(self):
        self._test([], [])

    def test_no0(self):
        self._test([1, 1, 1, ], [])

    def test_0in0_withSuc(self):
        self._test([0, 1, 1, ], [0, ])

    def test_0in0_noSuc(self):
        self._test([0], [0, ])

    def test_0in1_withSuc(self):
        self._test([1, 0, 1, ], [1, ])

    def test_0in1_noSuc(self):
        self._test([1, 0], [1, ])

    def test_0in2_withSuc(self):
        self._test([1, 1, 0, 1, ], [2, ])

    def test_0in2_noSuc(self):
        self._test([1, 1, 0], [2, ])


PreprocLoopMultiExit_TCs = [
    PreprocLoopMultiExit_singleExit0_TC,
    #PreprocLoopMultiExit_singleExit1_TC,
    PreprocLoopMultiExit_hwBreak0_TC,
]

if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    u = PreprocLoopMultiExit_singleExit0()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))

    suite = unittest.TestSuite()
    #suite.addTest(PreprocLoopMultiExit_hwBreak0_TC('test_0in2_withSuc'))
    for tc in PreprocLoopMultiExit_TCs:
        suite.addTest(unittest.makeSuite(tc))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
