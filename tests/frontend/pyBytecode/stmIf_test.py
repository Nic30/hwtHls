#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.stmIf import HlsConnectionFromPyIf, \
    HlsConnectionFromPyIfElse, HlsConnectionFromPyIfElsePreproc, \
    HlsConnectionFromPyIfElifElse


class StmIf_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsConnectionFromPyIf_ll(self):
        self._test_ll(HlsConnectionFromPyIf)
        
    def test_HlsConnectionFromPyIfElse_ll(self):
        self._test_ll(HlsConnectionFromPyIfElse)
        
    def test_HlsConnectionFromPyIfElsePreproc_ll(self):
        self._test_ll(HlsConnectionFromPyIfElsePreproc)
        
    def test_HlsConnectionFromPyIfElifElse_ll(self):
        self._test_ll(HlsConnectionFromPyIfElifElse)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([StmIf_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(StmIf_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
