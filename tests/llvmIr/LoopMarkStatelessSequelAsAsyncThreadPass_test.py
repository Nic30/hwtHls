#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function, ModulePassManager, \
    LoopMarkStatelessSequelAsAsyncThreadPass
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


def _LoopMarkStatelessSequelAsAsyncThreadPass(MPM: ModulePassManager):
    MPM.addPass(LoopMarkStatelessSequelAsAsyncThreadPass(applyOnAll=True))


class LoopMarkStatelessSequelAsAsyncThreadPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._runCustomModulePass(_LoopMarkStatelessSequelAsAsyncThreadPass)

    def test_noLoop(self):
        llvmIr = """\
        define void @test_noLoop() {
        bb.0:
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_nothingToExtract(self):
        llvmIr = """\
        define void @test_nothingToExtract(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.0:
          br label %bb.1
        bb.1:
           %i0 = load volatile i1, ptr addrspace(1) %i, align 1
           store volatile i1 %i0, ptr addrspace(2) %o, align 1
           br label %bb.1
        }
        """
        self._test_ll(llvmIr)

    def test_nothingToExtractNoState(self):
        llvmIr = """\
        define void @test_nothingToExtractNoState(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.0:
          br label %bb.1
        bb.1:
           %v0 = load volatile i8, ptr addrspace(1) %i, align 1
           %v1 =  add i8 %v0, 1
           store volatile i8 %v1, ptr addrspace(2) %o, align 1
           br label %bb.1
        }
        """
        self._test_ll(llvmIr)

    def test_nothingToExtractJustStore(self):
        llvmIr = """\
        define void @test_nothingToExtractJustStore(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.0:
          br label %bb.1
        bb.1:
           %acc = phi i8 [ 0, %bb.0 ], [ %v1, %bb.1 ]
           %v0 = load volatile i8, ptr addrspace(1) %i, align 1
           %v1 =  add i8 %v0, %acc
           store volatile i8 %v1, ptr addrspace(2) %o, align 1
           br label %bb.1
        }
        """
        self._test_ll(llvmIr)

    def test_noBranch(self):
        llvmIr = """\
        define void @test_noBranch(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.0:
          br label %bb.1
        bb.1:
           %acc = phi i8 [ 0, %bb.0 ], [ %v0, %bb.1 ]
           %v0 = load volatile i8, ptr addrspace(1) %i, align 1
           %v1 =  add i8 %v0, %acc
           store volatile i8 %v1, ptr addrspace(2) %o, align 1
           br label %bb.1
        }
        """
        self._test_ll(llvmIr)

    def test_noBranch_assume(self):
        llvmIr = """\
        define void @test_noBranch_assume(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.0:
          br label %bb.1
        bb.1:
           %acc = phi i8 [ 0, %bb.0 ], [ %v0, %bb.1 ]
           %v0 = load volatile i8, ptr addrspace(1) %i, align 1
           %v1 =  add i8 %v0, %acc
           store volatile i8 %v1, ptr addrspace(2) %o, align 1
           %a = icmp ne i8 %v0, 0 ; should stay in original code
           call void @llvm.assume(i1 %a) ; should stay in original code
           br label %bb.1
        }
        """
        self._test_ll(llvmIr)

    def test_3blockBrcond_singleEntry(self):
        llvmIr = """\
        define void @test_3blockBrcond_singleEntry(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.0:
          br label %bb.1
        bb.1:
           %acc = phi i8 [ 0, %bb.0 ], [ %v0, %bb.1.t ], [ %v0, %bb.1.f ]
           %v0 = load volatile i8, ptr addrspace(1) %i, align 1
           %c0 = icmp eq i8 %v0, 1
           %v1 =  add i8 %v0, %acc
           br i1 %c0, label %bb.1.t, label %bb.1.f
        bb.1.t:
           store volatile i8 %v1, ptr addrspace(2) %o, align 1
           br label %bb.1
        bb.1.f:
           br label %bb.1
        }
        """
        self._test_ll(llvmIr)

    def test_3blockBrcond_2Entry(self):
        llvmIr = """\
        define void @test_3blockBrcond_2Entry(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.0:
          br label %bb.1
        bb.1:
           %acc = phi i8 [ 0, %bb.0 ], [ %v0, %bb.1.t ], [ %v0, %bb.1.f ]
           %v0 = load volatile i8, ptr addrspace(1) %i, align 1
           %c0 = icmp eq i8 %v0, 1
           br i1 %c0, label %bb.1.t, label %bb.1.f
        bb.1.t:
           %v1 = add i8 %v0, %acc
           store volatile i8 %v1, ptr addrspace(2) %o, align 1
           br label %bb.1
        bb.1.f:
           %v2 = add i8 %v0, %v0
           store volatile i8 %v2, ptr addrspace(2) %o, align 1
           br label %bb.1
        }
        """
        self._test_ll(llvmIr)

    def test_3blockBrcond_2EntryNonDom(self):
        #  %v0.t, %v0.f sinked even if they should not
        llvmIr = """\
        define void @test_3blockBrcond_2EntryNonDom(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.0:
          br label %bb.1
        bb.1:
           %acc = phi i8 [ 0, %bb.0 ], [ %v0, %bb.1.t.0 ], [ %v0, %bb.1.f.0 ]
           %v0 = load volatile i8, ptr addrspace(1) %i, align 1
           %c0 = icmp eq i8 %v0, 1
           br i1 %c0, label %bb.1.t, label %bb.1.f
        bb.1.t:
           %v0.t = load volatile i8, ptr addrspace(1) %i, align 1
           br label %bb.1.t.0
        bb.1.t.0:
           %v1 = add i8 %v0.t, %acc
           store volatile i8 %v1, ptr addrspace(2) %o, align 1
           br label %bb.1
        bb.1.f:
           %v0.f = load volatile i8, ptr addrspace(1) %i, align 1
           br label %bb.1.f.0
        bb.1.f.0:
           %v2 = add i8 %v0, %v0.f
           store volatile i8 %v2, ptr addrspace(2) %o, align 1
           br label %bb.1
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(LoopMarkStatelessSequelAsAsyncThreadPass_TC)
    # suite = unittest.TestSuite([LoopMarkStatelessSequelAsAsyncThreadPass_TC('test_noBranch_assume')])
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
