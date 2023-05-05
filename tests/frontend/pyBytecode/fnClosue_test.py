#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.fnClosure import FnClosureSingleItem, FnClosureNone0, \
    FnClosureNone1


class FnClosure_TC(BaseSsaTC):
    __FILE__ = __file__
    FRONTEND_ONLY = True


    def test_FnClosureSingleItem_ll(self):
        self._test_ll(FnClosureSingleItem)
        
    def test_FnClosureNone0_ll(self):
        self._test_ll(FnClosureNone0)
        
    def test_FnClosureNone1_ll(self):
        self._test_ll(FnClosureNone1)


if __name__ == "__main__":
    import unittest
    
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FnClosure_TC('test_frameHeader')])
    suite = testLoader.loadTestsFromTestCase(FnClosure_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
