#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.stmWhile import HlsPythonHwWhile0, \
    HlsPythonHwWhile1, HlsPythonHwWhile2


class StmWhile_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsPythonHwWhile0_ll(self):
        self._test_ll(HlsPythonHwWhile0)
        
    def test_HlsPythonHwWhile1_ll(self):
        self._test_ll(HlsPythonHwWhile1)

    def test_HlsPythonHwWhile2_ll(self):
        self._test_ll(HlsPythonHwWhile2)

      
if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([StmWhile_TC("test_HlsPythonHwWhile0_ll")])
    suite = testLoader.loadTestsFromTestCase(StmWhile_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
