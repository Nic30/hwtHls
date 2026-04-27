#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, verifyModule, Module, ModulePassManager, \
    ThreadExtractIoFsmPass, StripDeadPrototypesPass
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.StreamReadLoweringPass_test import StreamReadLoweringPass_TC
from unittest.case import expectedFailure


def _addThreadExtractIoFsmPass(MPM: ModulePassManager):
    MPM.addPass(ThreadExtractIoFsmPass())
    MPM.addPass(StripDeadPrototypesPass())


class ThreadExtractIoFsmPass_ir_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Module:
        M = llvm._runCustomModulePass(_addThreadExtractIoFsmPass)
        if verifyModule(M):
            raise AssertionError()
        return M

    def _test_ir_file(self):
        StreamReadLoweringPass_TC._test_ir_file(self)

    def test_1loop(self):
        self._test_ir_file()

    @expectedFailure  # NotImplemented for in
    def test_1loop_in(self):
        self._test_ir_file()

    @expectedFailure  # NotImplemented for in
    def test_1loop_in_bitRangeGet(self):
        self._test_ir_file()

    def test_1loop_bitRangeGet(self):
        self._test_ir_file()

    def test_2loopNested(self):
        self._test_ir_file()

    def test_2loopNested2(self):
        # this has liveout from section before child header to section after child loop but still inside of parent loop
        self._test_ir_file()


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ThreadExtractIoFsmPass_ir_TC('test_1loop_in')])
    suite = testLoader.loadTestsFromTestCase(ThreadExtractIoFsmPass_ir_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
