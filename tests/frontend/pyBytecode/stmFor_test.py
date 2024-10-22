#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.stmFor import HlsPythonPreprocFor, \
    HlsPythonPreprocForPreprocWhile, HlsPythonPreprocFor2x_0, \
    HlsPythonPreprocFor2x_1, HlsPythonPreprocForInIf0, HlsPythonPreprocForInIf1, \
    HlsPythonPreprocForInIf2


class StmFor_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsPythonPreprocFor_ll(self):
        self._test_ll(HlsPythonPreprocFor)
    
    def test_HlsPythonPreprocForInIf0_ll(self):
        self._test_ll(HlsPythonPreprocForInIf0)

    def test_HlsPythonPreprocForInIf0_False_ll(self):
        m = HlsPythonPreprocForInIf0()
        m.IF_COND = False
        self._test_ll(m, name=m.__class__.__name__ + "_False")

    def test_HlsPythonPreprocForInIf1_ll(self):
        self._test_ll(HlsPythonPreprocForInIf1)

    def test_HlsPythonPreprocForInIf1_False_ll(self):
        m = HlsPythonPreprocForInIf1()
        m.IF_COND = False
        self._test_ll(m, name=m.__class__.__name__ + "_False")

    def test_HlsPythonPreprocForInIf2_ll(self):
        self._test_ll(HlsPythonPreprocForInIf2)

    def test_HlsPythonPreprocForInIf2_False_ll(self):
        m = HlsPythonPreprocForInIf2()
        m.IF_COND = False
        self._test_ll(m, name=m.__class__.__name__ + "_False")


    def test_HlsPythonPreprocForPreprocWhile_ll(self):
        self._test_ll(HlsPythonPreprocForPreprocWhile)

    def test_HlsPythonPreprocFor2x_0_ll(self):
        self._test_ll(HlsPythonPreprocFor2x_0)

    def test_HlsPythonPreprocFor2x_1_ll(self):
        self._test_ll(HlsPythonPreprocFor2x_1)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([StmFor_TC("test_HlsPythonPreprocForInIf_False_ll")])
    suite = testLoader.loadTestsFromTestCase(StmFor_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
