#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.llvmMir.baseLlvmMirTC import BaseLlvmMirTC
from hwtHls.llvm.llvmIr import LlvmCompilationBundle


class EarlyIfConverter_TC(BaseLlvmMirTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle):
        llvm._testEarlyIfConverter()

    def test_mergeExitBlockOfParentLoop(self):
        self._test_mir_file()

    # def test_branchWithOptionalStore(self):
    #    self._test_mir_file()
    #
    # def test_2branchesWithSameStore(self):
    #    self._test_mir_file()


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([EarlyIfConverter_TC('test_mergeExitBlockOfParentLoop')])
    suite = testLoader.loadTestsFromTestCase(EarlyIfConverter_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
