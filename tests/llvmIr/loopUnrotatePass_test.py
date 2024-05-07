#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class LoopUnrotatePass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._testLoopUnrotatePass()

    def test_phiInGuard(self):
        llvmIr = """\
            define void @phiInGuard(ptr addrspace(1) %c, ptr addrspace(2) %o) {
            entry:
              br label %guard
            
            guard:
              %vInGuard = phi i2 [3, %entry], [0, %guardExit]
              %c0 = load volatile i1, ptr addrspace(1) %c, align 1
              br i1 %c0, label %loopHeader, label %guardExit
            
            loopHeader:
              %v = phi i2 [ %vInGuard, %guard ], [ %v, %loopHeader ]
              %c1 = load volatile i1, ptr addrspace(1) %c, align 1
              br i1 %c1, label %loopHeader, label %guardExit
            
            guardExit:
              %vInGuardExit = phi i2 [ %v, %loopHeader ], [ %vInGuard, %guard ]
              store volatile i2 %vInGuardExit, ptr addrspace(2) %o, align 1
              br label %guard
            }
        """
        self._test_ll(llvmIr)

    def test_ShifterLeftBarrelUsingHwLoop(self):
        # :note: this should not be iunrotated because i0, sh1 are not copied
        llvmIr = """\
            define void @ShifterLeftBarrelUsingHwLoop(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %sh) {
            entry:
              br label %bb0
            
            bb0:
              %i0 = load volatile i2, ptr addrspace(1) %i, align 1
              %sh1 = load volatile i1, ptr addrspace(3) %sh, align 1
              %"2" = icmp ne i1 %"sh1", false
              br i1 %"2", label %bb1, label %bb2
            
            bb1:
              %"v.3" = phi i2 [ %i0, %bb0 ], [ %1, %bb1 ]
              %0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %"v.3", i2 0) #2
              %1 = call i2 @hwtHls.bitConcat.i1.i1(i1 false, i1 %0) #2
              %"7" = icmp ne i1 %sh1, false
              br i1 %"7", label %bb1, label %bb2
            
            bb2:
              %"v.9" = phi i2 [ %1, %bb1 ], [ %i0, %bb0 ]
              store volatile i2 %"v.9", ptr addrspace(2) %o, align 1
              br label %bb0
            }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([LoopUnrotatePass_TC('test_phiInGuard')])
    suite = testLoader.loadTestsFromTestCase(LoopUnrotatePass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
