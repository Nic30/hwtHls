#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, parseIR, verifyModule
from tests.llvmIr.baseLlvmIrTC import generateAndAppendHwtHlsFunctionDeclarations


class MergeSetsBasedLivenessAnalysis_TC(unittest.TestCase):
    __FILE__ = __file__

    def _test_ll(self, irStr: str, llvmCliArgs=[], passArgs=(), passKwArgs={}, use_generateAndAppendHwtHlsFunctionDeclarations=True):
        if use_generateAndAppendHwtHlsFunctionDeclarations:
            irStr = generateAndAppendHwtHlsFunctionDeclarations(irStr)
        llvm = LlvmCompilationBundle("test", llvmCliArgs)
        Err = SMDiagnostic()
        M = parseIR(irStr, "test", Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            llvm.module = M
            llvm._tryToFindMain()
        if verifyModule(M):
            raise AssertionError("Module is already invalid before the test")
        return llvm._testMergeSetsBasedLivenessAnalysis()

    def test_duplicatedSucc(self):
        llvmIr = """\
        define void @test_duplicatedSucc(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          br label %bb.head
        
        bb1:                                          ; preds = %bb.head, %bb.head
          ; :note: it is important that the bb1 is exactly on this possition
          br i1 false, label %bb2, label %bb.latch
        
        bb.head:                                              ; preds = %bb.latch, %bb0
          switch i16 0, label %bb2 [
            i16 3, label %bb1
            i16 4, label %bb1
          ]

        bb2:                                                ; preds = %bb.head, %bb1
          br label %bb.latch
        
        bb.latch:                                                ; preds = %bb2, %bb1
          br label %bb.head
        }
        """
        #from tests.stripInstructionsUnrelatedToCrash import llmIrStripInstrucionsUnrelatedToCrash
        #llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: llvm._testMergeSetsBasedLivenessAnalysis(), logAfterChange=True, timeout=1.)
        #print(str(llvm.main))
        self._test_ll(llvmIr)


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(MergeSetsBasedLivenessAnalysis_TC)
    suite = unittest.TestSuite([MergeSetsBasedLivenessAnalysis_TC('test_duplicatedSucc')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

