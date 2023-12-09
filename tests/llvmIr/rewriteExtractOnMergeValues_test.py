#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, parseIR
from tests.baseSsaTest import BaseSsaTC
from tests.llvmIr.slicesMergePass_test import generateAndAppendHwtHlsFunctionDeclarations


class RewriteExtractOnMergeValuesPass_TC(BaseSsaTC):
    __FILE__ = __file__

    def _test_ll(self, irStr: str):
        irStr = generateAndAppendHwtHlsFunctionDeclarations(irStr)
        llvm = LlvmCompilationBundle("test")
        Err = SMDiagnostic()
        M = parseIR(irStr, "test", Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            fns = tuple(M)
            llvm.module = M
            llvm.main = fns[0]
            name = llvm.main.getName().str()

        optF = llvm._testRewriteExtractOnMergeValuesPass()
        self.assert_same_as_file(repr(optF), os.path.join("data", self.__class__.__name__ + '.' + name + ".ll"))

    def test_sliceBr(self):
        llvmIr = """\
            define void @sliceBr(ptr addrspace(1) %dataIn) {
            bb.0:
              %0 = load volatile i19, ptr addrspace(1) %dataIn, align 4
              %1 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %0, i6 17) #2
              %2 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %0, i6 16) #2
              %3 = call i8 @hwtHls.bitRangeGet.i19.i6.i8.0(i19 %0, i6 0) #2
              %4 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %0, i6 18) #2
              %5 = xor i1 %1, true
              %6 = and i1 %4, %5
              %7 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %3, i1 %2, i1 %6) #2
              %8 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %7, i5 9) #2
              br i1 %8, label %bb.1, label %bb.2
            bb.1:
              ret void
            bb.2:
              ret void
            }
        """
        self._test_ll(llvmIr)

if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([RewriteExtractOnMergeValuesPass_TC('test_sliceBr')])
    suite = testLoader.loadTestsFromTestCase(RewriteExtractOnMergeValuesPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
