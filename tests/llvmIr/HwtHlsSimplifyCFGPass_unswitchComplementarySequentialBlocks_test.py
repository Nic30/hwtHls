#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsSimplifyCFGPass_test import HwtHlsSimplifyCFGPass_TC


class HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return HwtHlsSimplifyCFGPass_TC._runTestOpt(self, llvm)

    def test_HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_tryHoistFromBB1_0(self):
        llvmIr = """\
        define void @test_HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_tryHoistFromBB1_0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bbentry:
          br label %bbHead
        bbHead:
          br label %bb0
        bb0:
          %c = load volatile i1, ptr addrspace(1) %i, align 4
          %v0 = load volatile i1, ptr addrspace(1) %i, align 4
          %v1 = load volatile i8, ptr addrspace(1) %i, align 4
          
          br i1 %c, label %bbC0, label %bb1

        bbC0:                           ; preds = %bb0
          store volatile i8 0, ptr addrspace(2) %o, align 4
          br label %bb1
        
        bb1:                                               ; preds = %bb0, %bbC0
          call void @llvm.assume(i1 %v0), !hwthls.sideeffect.allowhoist !5
          %v1.1 = add nuw i8 %v1, 3
          br i1 %c, label %bbExit, label %bbC1
        
        bbC1:                                  ; preds = %bb1
          store volatile i8 1, ptr addrspace(2) %o, align 4
          br label %bbLatch
          
        bbExit:
          store volatile i8 %v1.1, ptr addrspace(2) %o, align 4
          br label %bbLatch
        
        bbLatch:
          br label %bbHead
        }
        !5 = !{}
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_TC)
    # suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_TC('test_0')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
