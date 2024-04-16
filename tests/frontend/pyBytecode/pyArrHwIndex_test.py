#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from io import StringIO
import os

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from tests.baseSsaTest import BaseSsaTC, TestFinishedSuccessfuly, BaseTestPlatform
from tests.frontend.pyBytecode.pyArrHwIndex import Rom, CntrArray


class CntrArrayWithCfgDotDump(CntrArray):

    def _config(self) -> None:
        CntrArray._config(self)
        self.CFG_FILE = None

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        t = hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        try:
            hls.compile()
        finally:
            sealedBlocks = set(t.bytecodeToSsa.blockToLabel[b] for b in t.bytecodeToSsa.toSsa.m_ssa_u.sealedBlocks)
            t.bytecodeToSsa.callStack[-1].blockTracker.dumpCfgToDot(self.CFG_FILE, sealedBlocks, t.bytecodeToSsa.labelToBlock)
            

class PyArrHwIndex_TC(BaseSsaTC):
    __FILE__ = __file__
    TEST_THREADS_AND_SYNC = False

    def test_Rom_ll(self):
        self._test_ll(Rom)
        
    def test_CntrArray_ll(self):
        self._test_ll(CntrArray)

    def test_CntrArray_cfgDot(self):
        buff = StringIO()

        class FrontendTestPlatform(BaseTestPlatform):

            def runSsaPasses(self, hls:"HlsScope", toSsa:HlsAstToSsa):
                raise TestFinishedSuccessfuly()

        u = CntrArrayWithCfgDotDump()
        u.CFG_FILE = buff
        self._runTranslation(u, FrontendTestPlatform())
        self.assert_same_as_file(buff.getvalue(), os.path.join("data", "CntrArray_cfg.dot"))


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PyArrHwIndex_TC("test_CntrArray_ll")])
    suite = testLoader.loadTestsFromTestCase(PyArrHwIndex_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
