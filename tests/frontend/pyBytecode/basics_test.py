#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.simulator.simTestCase import SimTestCase
from hwt.hwModule import HwModule
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.frontend.pyBytecode.basics import HlsConnectionFromPyFn0, \
    HlsConnectionFromPyFn1, HlsConnectionFromPyFnTmpVar, HlsConnectionFromPyFnIf, \
    HlsConnectionFromPyFnElif, HlsConnectionFromPyFnIfTmpVar, HlsConnectionFromPyFnPreprocTmpVar0, \
    HlsConnectionFromPyFnPreprocTmpVar1


class FromPythonBasics_TC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def _test_connection(self, cls: Type[HwModule], ref, CLK=10):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.i._ag.data.extend(range(CLK))

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, ref)

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
    #from hwt.synth import to_rtl_str
    #from hwtHls.platform.platform import HlsDebugBundle
    #
    #m = HlsConnectionFromPyFnIf()
    #print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FromPythonBasics_TC('test_HlsConnectionFromPyFnIf')])
    suite = testLoader.loadTestsFromTestCase(FromPythonBasics_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
