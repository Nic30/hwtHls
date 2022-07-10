#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.frontend.pyBytecode.basics import HlsConnectionFromPyFn0, \
    HlsConnectionFromPyFn1, HlsConnectionFromPyFnTmpVar, HlsConnectionFromPyFnIf, \
    HlsConnectionFromPyFnElif, HlsConnectionFromPyFnIfTmpVar, HlsConnectionFromPyFnPreprocTmpVar0, \
    HlsConnectionFromPyFnPreprocTmpVar1


class FromPythonBasics_TC(SimTestCase):

    def _test_no_comb_loops(self):
        HlsAstTrivial_TC._test_no_comb_loops(self)

    def _test_connection(self, cls: Type[Unit], ref, CLK=10):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.i._ag.data.extend(range(CLK))

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)

    def test_HlsConnectionFromPyFn0(self):
        self._test_connection(HlsConnectionFromPyFn0, list(range(10)))

    def test_HlsConnectionFromPyFnTmpVar(self):
        self._test_connection(HlsConnectionFromPyFnTmpVar, list(range(10)))

    def test_HlsConnectionFromPyFnPreprocTmpVar0(self):
        self._test_connection(HlsConnectionFromPyFnPreprocTmpVar0, list(range(10)))

    def test_HlsConnectionFromPyFnPreprocTmpVar1(self):
        self._test_connection(HlsConnectionFromPyFnPreprocTmpVar1, list(range(10)))

    def test_HlsConnectionFromPyFn1(self):
        self._test_connection(HlsConnectionFromPyFn1, [i << 4 for i in range(10)])

    def test_HlsConnectionFromPyFnIfTmpVar(self):
        self._test_connection(HlsConnectionFromPyFnIfTmpVar, [10 if i == 3 else 11 for i in range(10)])

    def test_HlsConnectionFromPyFnIf(self):
        self._test_connection(HlsConnectionFromPyFnIf, [10 if i == 3 else 11 for i in range(10)])

    def test_HlsConnectionFromPyFnElif(self):
        self._test_connection(HlsConnectionFromPyFnElif, [10 if i == 3 else 11 if i == 4 else 12 for i in range(10)])


if __name__ == "__main__":
    import unittest
    #from hwt.synthesizer.utils import to_rtl_str
    #
    #u = HlsConnectionFromPyFnIf()
    #print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))

    suite = unittest.TestSuite()
    # suite.addTest(FromPythonBasics_TC('test_HlsConnectionFromPyFnIf'))
    suite.addTest(unittest.makeSuite(FromPythonBasics_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
