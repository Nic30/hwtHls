#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.simulator.simTestCase import SimTestCase
from hwt.simulator.utils import valToInt
from hwt.synthesizer.unit import Unit
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.readAtleastOne import ReadAtleastOneOf2, ReadAtleastOneOf3


class ReadAtleastOne_TC(SimTestCase):

    def _test_no_comb_loops(self):
        HlsAstTrivial_TC._test_no_comb_loops(self)

    def _test_ReadAtleastOne(self, cls: Type[Unit], N: int, inputCnt:int):
        assert N % inputCnt == 0, (N, inputCnt)
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        for i in range(inputCnt):
            inp = getattr(u, f"i{i:d}")
            inp._ag.data.extend(range(i * (N // inputCnt), (i + 1) * (N // inputCnt)))
            self.randomize(inp)
        self.randomize(u.o)
        self.runSim(4 * N * CLK_PERIOD)
        self._test_no_comb_loops()
        d = [valToInt(v) for v in u.o._ag.data]
        d.sort(key=lambda x:-1 if x is None else x)
        self.assertListEqual(d, list(range(N)))

    def test_ReadAtleastOneOf2(self, cls=ReadAtleastOneOf2):
        self._test_ReadAtleastOne(cls, 16, 2)

    def test_ReadAtleastOneOf3(self, cls=ReadAtleastOneOf3):
        self._test_ReadAtleastOne(cls, 24, 3)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = ReadAtleastOneOf3()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL)))
    
    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(ReadAtleastOne_TC('test_ReadAtleastOneOf3'))
    suite.addTest(unittest.makeSuite(ReadAtleastOne_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
 
