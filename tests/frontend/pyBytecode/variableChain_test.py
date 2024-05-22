#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.variableChain import VariableChain


class VariableChain_TC(BaseSsaTC):
    __FILE__ = __file__
    TEST_THREADS_AND_SYNC = False

    def test_VariableChain1_ll(self):

        def VariableChain_1():
            m = VariableChain()
            m.LEN = 1
            return m

        self._test_ll(VariableChain_1, name="VariableChain_1")

    def test_VariableChain3_ll(self):

        def VariableChain_3():
            m = VariableChain()
            m.LEN = 3
            return m

        self._test_ll(VariableChain_3, name="VariableChain_3")


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([VariableChain_TC("test_VariableChain3_ll")])
    suite = testLoader.loadTestsFromTestCase(VariableChain_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
