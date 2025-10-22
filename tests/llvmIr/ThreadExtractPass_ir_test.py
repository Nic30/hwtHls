#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function, verifyModule, \
    ModulePassManager, ThreadExtractPass, StripDeadPrototypesPass
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.StreamReadLoweringPass_test import StreamReadLoweringPass_TC


def _addThreadExtractPass(MPM: ModulePassManager):
    MPM.addPass(ThreadExtractPass())
    MPM.addPass(StripDeadPrototypesPass())


class ThreadExtractPass_ir_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        M = llvm._runCustomModulePass(_addThreadExtractPass)
        if verifyModule(M):
            raise AssertionError()
        return M

    def _test_ir_file(self):
        StreamReadLoweringPass_TC._test_ir_file(self)

    def test_noDepsSyncNone(self):
        self._test_ir_file()

    def test_noDepsSyncBeginEnd(self):
        self._test_ir_file()

    def test_inDepsSyncBeginEnd(self):
        self._test_ir_file()

    def test_outDepsSyncBeginEnd(self):
        self._test_ir_file()


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ThreadExtractPass_ir_TC('test_outDepsSyncBeginEnd')])
    suite = testLoader.loadTestsFromTestCase(ThreadExtractPass_ir_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
