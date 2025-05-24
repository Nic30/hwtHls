#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from io import StringIO
import os

from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from tests.baseSsaTest import BaseSsaTC, TestFinishedSuccessfuly, BaseTestPlatform
from tests.frontend.pyArrHwIndex import ExampleRomPyList, ExampleCntrArray, \
    ExampleRomHwArray, ExampleCntrArrayHwArray, ExampleCam


class ExampleCntrArrayWithCfgDotDump(ExampleCntrArray):

    def hwConfig(self) -> None:
        ExampleCntrArray.hwConfig(self)
        self.CFG_FILE = None

    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        t = hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        try:
            hls.compile()
        finally:
            t.bytecodeToSsa.callStack[-1].blockTracker.dumpCfgToDot(self.CFG_FILE, {}, t.bytecodeToSsa.labelToBlock)


class PyArrHwIndex_TC(BaseSsaTC):
    __FILE__ = __file__
    TEST_BLOCK_SYNC = False

    def test_ExampleRomPyList_ll(self):
        self._test_ll(ExampleRomPyList)

    def test_ExampleRomHwArray_ll(self):
        self._test_ll(ExampleRomHwArray)

    def test_ExampleCntrArray_ll(self):
        # :note: MUXes at end are mirrored (does not affect functionality) because InstCombinePass ordered i_read icmp in this way
        self._test_ll(ExampleCntrArray)

    def test_ExampleCntrArrayHwArray_ll(self):
        self._test_ll(ExampleCntrArrayHwArray)

    def test_ExampleCam_ll(self):
        self._test_ll(ExampleCam)

    def test_ExampleCntrArray_cfgDot(self):
        buff = StringIO()

        class FrontendTestPlatform(BaseTestPlatform):

            def runSsaPasses(self, hls:"HlsScope", tpLllvm:ToLlvmIrTranslator):
                raise TestFinishedSuccessfuly()

        m = ExampleCntrArrayWithCfgDotDump()
        m.CFG_FILE = buff
        self._runTranslation(m, FrontendTestPlatform())
        self.assert_same_as_file(buff.getvalue(), os.path.join("data", "CntrArray_cfg.dot"))


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PyArrHwIndex_TC("test_ExampleCntrArray_ll")])
    suite = testLoader.loadTestsFromTestCase(PyArrHwIndex_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
