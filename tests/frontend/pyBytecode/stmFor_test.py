#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.stmFor import HlsPythonPreprocFor, \
    HlsPythonPreprocForPreprocWhile, HlsPythonPreprocFor2x_0, \
    HlsPythonPreprocFor2x_1


class StmFor_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsPythonPreprocFor_ll(self):
        self._test_ll(HlsPythonPreprocFor)

    def test_HlsPythonPreprocForPreprocWhile_ll(self):
        self._test_ll(HlsPythonPreprocForPreprocWhile)

    def test_HlsPythonPreprocFor2x_0_ll(self):
        self._test_ll(HlsPythonPreprocFor2x_0)

    def test_HlsPythonPreprocFor2x_1_ll(self):
        self._test_ll(HlsPythonPreprocFor2x_1)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([StmFor_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(StmFor_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
