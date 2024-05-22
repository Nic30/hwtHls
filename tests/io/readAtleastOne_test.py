#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.simulator.simTestCase import SimTestCase
from hwt.simulator.utils import Bits3valToInt
from hwt.hwModule import HwModule
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.readAtleastOne import ReadAtleastOneOf2, ReadAtleastOneOf3


class ReadAtleastOne_TC(SimTestCase):

    def _test_no_comb_loops(self):
        HlsAstTrivial_TC._test_no_comb_loops(self)

    def _test_ReadAtleastOne(self, cls: Type[HwModule], N: int, inputCnt:int):
        assert N % inputCnt == 0, (N, inputCnt)
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        for i in range(inputCnt):
            inp = getattr(dut, f"i{i:d}")
            inp._ag.data.extend(range(i * (N // inputCnt), (i + 1) * (N // inputCnt)))
            self.randomize(inp)
        self.randomize(dut.o)
        self.runSim(4 * N * CLK_PERIOD)
        self._test_no_comb_loops()
        d = [Bits3valToInt(v) for v in dut.o._ag.data]
        d.sort(key=lambda x:-1 if x is None else x)
        self.assertListEqual(d, list(range(N)))

    def test_ReadAtleastOneOf2(self, cls=ReadAtleastOneOf2):
        self._test_ReadAtleastOne(cls, 16, 2)

    def test_ReadAtleastOneOf3(self, cls=ReadAtleastOneOf3):
        self._test_ReadAtleastOne(cls, 24, 3)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = ReadAtleastOneOf3()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ReadAtleastOne_TC("test_ReadAtleastOneOf3")])
    suite = testLoader.loadTestsFromTestCase(ReadAtleastOne_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

