#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.llvmLoopUnroll import InfLoopUnrollDissable, \
    InfLoopUnrollCount


class LlvmLoopUnroll_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_InfLoopUnrollDissable_ll(self):
        self._test_ll(InfLoopUnrollDissable)

    def test_InfLoopUnrollCount_ll(self):
        self._test_ll(InfLoopUnrollCount) 


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(LlvmLoopUnroll_TC('test_InfLoopUnrollDissable_ll'))
    suite.addTest(unittest.makeSuite(LlvmLoopUnroll_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
