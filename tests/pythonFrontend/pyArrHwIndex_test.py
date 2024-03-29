#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from io import StringIO
import os

from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.transformation.runFn import SsaPassRunFn
from tests.baseSsaTest import BaseSsaTC, TestFinishedSuccessfuly
from tests.pythonFrontend.pyArrHwIndex import Rom, CntrArray
from hwtHls.ssa.translation.fromPython.thread import HlsStreamProcPyThread


class CntrArrayWithCfgDotDump(CntrArray):

    def _config(self) -> None:
        CntrArray._config(self)
        self.CFG_FILE = None

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        t = hls.thread(HlsStreamProcPyThread(hls, self.mainThread, hls))
        try:
            hls.compile()
        finally:
            t.bytecodeToAst.blockTracker.dumpCfgToDot(self.CFG_FILE)
            

class PyArrHwIndex_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_Rom_ll(self):
        self._test_ll(Rom)
        
    def test_CntrArray_ll(self):
        self._test_ll(CntrArray)

    def test_CntrArray_cfgDot(self):
        buff = StringIO()
        ssa_passes = [
            SsaPassRunFn(TestFinishedSuccessfuly.raise_)
        ]
        u = CntrArrayWithCfgDotDump()
        u.CFG_FILE = buff
        self._runTranslation(u, ssa_passes)
        self.assert_same_as_file(buff.getvalue(), os.path.join("data", "CntrArray_cfg.dot"))


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(PyArrHwIndex_TC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(PyArrHwIndex_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
