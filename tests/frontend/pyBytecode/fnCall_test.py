#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.fnCall import FnCallFn, FnCallFnRet, FnCallFnArgs, \
    FnCallFnKwArgs, FnCallFnArgsKwArgs, FnCallFnArgsKwArgsSomeDefault, \
    FnCallMethod, FnCallMethodArgsKwArgsSomeDefault, FnCallFnArgsExpand, \
    FnCallFnVariadic, FnCallFnVariadicExpand, FnCallFnVariadicExpandKwArgs, \
    FnCallFnVariadicExpandKwArgsExpand


class FnCall_TC(BaseSsaTC):
    __FILE__ = __file__
    FRONTEND_ONLY = True

    def test_FnCallFn_ll(self):
        self._test_ll(FnCallFn)
        
    def test_FnCallFnRet_ll(self):
        self._test_ll(FnCallFnRet)
        
    def test_FnCallFnArgs_ll(self):
        self._test_ll(FnCallFnArgs)
        
    def test_FnCallFnArgsExpand_ll(self):
        self._test_ll(FnCallFnArgsExpand)

    def test_FnCallFnKwArgs_ll(self):
        self._test_ll(FnCallFnKwArgs)

    def test_FnCallFnArgsKwArgs_ll(self):
        self._test_ll(FnCallFnArgsKwArgs)

    def test_FnCallFnArgsKwArgsSomeDefault_ll(self):
        self._test_ll(FnCallFnArgsKwArgsSomeDefault)

    def test_FnCallMethod_ll(self):
        self._test_ll(FnCallMethod)

    def test_FnCallMethodArgsKwArgsSomeDefault_ll(self):
        self._test_ll(FnCallMethodArgsKwArgsSomeDefault)

    def test_FnCallFnVariadic_ll(self):
        self._test_ll(FnCallFnVariadic)

    def test_FnCallFnVariadicExpand_ll(self):
        self._test_ll(FnCallFnVariadicExpand)

    def test_FnCallFnVariadicExpandKwArgs_ll(self):
        self._test_ll(FnCallFnVariadicExpandKwArgs)

    def test_FnCallFnVariadicExpandKwArgsExpand_ll(self):
        self._test_ll(FnCallFnVariadicExpandKwArgsExpand)


if __name__ == "__main__":
    import unittest
    
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FnCall_TC('test_frameHeader')])
    suite = testLoader.loadTestsFromTestCase(FnCall_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
