#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.readSizeFromRamAndSendSequence import ReadSizeFromRamAndSendSequence


class ReadSizeFromRamAndSendSequence_TC(SimTestCase):

    def _test_no_comb_loops(self):
        HlsAstTrivial_TC._test_no_comb_loops(self)

    def test_ReadSizeFromRamAndSendSequence(self, FREQ=50e6):
        u = ReadSizeFromRamAndSendSequence()
        u.CLK_FREQ = int(FREQ)
        CLK = 8
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        indexSizeTuples = [
            (3, 4),
            (2, 1),
            (0, 2),
        ]
        u.index._ag.presetBeforeClk = True
        u.index._ag.data.extend(i for i, _ in indexSizeTuples)
        u.ram._ag.mem.update({k: v for k, v in indexSizeTuples})

        self.runSim(CLK * int(freq_to_period(FREQ)))
        self._test_no_comb_loops()
        ref = []
        for _, size in indexSizeTuples:
            ref.extend(range(size - 1, -1, -1))
        self.assertValSequenceEqual(u.out._ag.data, ref)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    u = ReadSizeFromRamAndSendSequence()
    u.CLK_FREQ = int(50e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
    
    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(ReadSizeFromRamAndSendSequence_TC('test_ReadSizeFromRamAndSendSequence'))
    suite.addTest(unittest.makeSuite(ReadSizeFromRamAndSendSequence_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
