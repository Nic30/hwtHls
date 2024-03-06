#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.llvmIr.llvmLoopUnroll import InfLoopUnrollDissable, \
    InfLoopUnrollCount


class LlvmLoopUnroll_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_InfLoopUnrollDissable_ll(self):
        self._test_ll(InfLoopUnrollDissable)

    def test_InfLoopUnrollCount_ll(self):
        self._test_ll(InfLoopUnrollCount)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([LlvmLoopUnroll_TC("test_InfLoopUnrollCount_ll")])
    suite = testLoader.loadTestsFromTestCase(LlvmLoopUnroll_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
