#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC
from tests.io.bram.counterArray import BramCounterArray0nocheck, \
    BramCounterArray1hardcodedlsu


class BramCounterArray_TC(BaseSsaTC):
    __FILE__ = __file__

    def _test_BramCounterArray(self, cls: Type[BramCounterArray0nocheck],
                               F=50e6, N=32, TIME_MULTIPLIER=2, randomize=True, mayLeak=False):
        # :param mayLeak: if true it is allowed that the value in memory is less than it is expected
        #     this is used for test where the increment of counter may be lost due to unhandled lolision check
        #     in the pipeline
        u = cls()
        u.CLK_FREQ = int(F)
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        mem = self.rtl_simulator.model.ram_inst.io.ram_memory
        ref = {i: 0 for i in range(u.ITEMS)}
        mem.val = mem.def_val = mem._dtype.from_py(ref)
        for _ in range(N):
            i = self._rand.randint(0, u.ITEMS - 1)
            ref[i] += 1
            u.incr._ag.data.append(i)

        if randomize:
            self.randomize(u.incr)

        self.runSim((TIME_MULTIPLIER * N + 10) * int(freq_to_period(u.CLK_FREQ)))
        self.assertEmpty(u.incr._ag.data)
        for i in range(u.ITEMS):
            d = mem.val.val.get(i, None)
            # print(i, ref[i], d)
            self.assertTrue(d is not None and d._is_full_valid(), ("index", i))
            if mayLeak:
                self.assertLessEqual(int(d), ref[i], ("index", i))
            else:
                self.assertEqual(int(d), ref[i], ("index", i))

    def test_BramCounterArray0nocheck(self):
        self._test_BramCounterArray(BramCounterArray0nocheck, mayLeak=True)

    def test_BramCounterArray1hardcodedlsu(self):
        self._test_BramCounterArray(BramCounterArray1hardcodedlsu, TIME_MULTIPLIER=3)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BramCounterArray_TC("test_BramCounterArray1hardcodedlsu")])
    suite = testLoader.loadTestsFromTestCase(BramCounterArray_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
