#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.counterArray import CounterArray


class CounterArray_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_CounterArray(self, N=32, randomize=True):
        u = CounterArray()
        u.CLK_FREQ = int(50e6)
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform(debugDir="tmp"))
        mem = self.rtl_simulator.model.ram_inst.io.ram_memory
        ref = {i: 0 for i in range(u.ITEMS)}
        mem.val = mem.def_val = mem._dtype.from_py(ref)
        for _ in range(N):
            i = self._rand.randint(0, u.ITEMS - 1)
            ref[i] += 1
            u.incr._ag.data.append(i)
        if randomize:
            self.randomize(u.incr)
        self.runSim((2*N + 10) * int(freq_to_period(u.CLK_FREQ)))
        for i in range(u.ITEMS):
            d = mem.val.val.get(i, None)
            self.assertValEqual(d, ref[i], ("index", i))


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(CounterArray_TC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(CounterArray_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
