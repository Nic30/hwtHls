#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.pythonFrontend.variableChain import VariableChain


class VariableChain_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_VariableChain1_ll(self):

        def VariableChain_1():
            u = VariableChain()
            u.LEN = 1
            return u
        
        self._test_ll(VariableChain_1, name="VariableChain_1")

    def test_VariableChain3_ll(self):

        def VariableChain_3():
            u = VariableChain()
            u.LEN = 3
            return u
        
        self._test_ll(VariableChain_3, name="VariableChain_3") 


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(VariableChain_TC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(VariableChain_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
