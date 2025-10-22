#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function, verifyFunction, \
    FunctionPassManager, StreamSegmentLoopUnrollPass
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.StreamReadLoweringPass_test import StreamReadLoweringPass_TC


def _addStreamSegmentLoopUnrollPass(FPM: FunctionPassManager):
    FPM.addPass(StreamSegmentLoopUnrollPass())


class StreamSegmentLoopUnrollPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        F = llvm._runCustomFunctionPass(_addStreamSegmentLoopUnrollPass)
        if verifyFunction(F):
            raise AssertionError()
        return F

    def _test_ir_file(self):
        StreamReadLoweringPass_TC._test_ir_file(self)

    def test_headerPop(self):
        self._test_ir_file()


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([StreamSegmentLoopUnrollPass_TC('test_noDepsSyncBeginEnd')])
    suite = testLoader.loadTestsFromTestCase(StreamSegmentLoopUnrollPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
