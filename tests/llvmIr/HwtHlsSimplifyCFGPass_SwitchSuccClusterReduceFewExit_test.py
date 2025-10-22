#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsSimplifyCFGPass_test import HwtHlsSimplifyCFGPass_TC


class HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return HwtHlsSimplifyCFGPass_TC._runTestOpt(self, llvm)

    def test_SwitchSuccClusterReduceFewExit_0(self):
        llvmIr = """\
        define void @test_SwitchSuccClusterReduceFewExit_0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb.entry:
          br label %bb.loop0.head

        bb.loop0.head:
          %e0 = load volatile i1, ptr addrspace(1) %i, align 4
          %c0 = load volatile i2, ptr addrspace(1) %i, align 4
          br label %bb.sw

        bb.sw:                         ; preds = %bb.loop0.head
          switch i2 %c0, label %bb.swUnreachable [
            i2 0, label %bb.swJump0
            i2 1, label %bb.swJump1
            i2 -2, label %bb.swJump2
          ]
        
        bb.swJump1:                               ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump2:                             ; preds = %bb.sw
          br i1 %e0, label %bb.loop0.head, label %bb.swJump0
        
        bb.swJump0:                          ; preds = %bb.sw, %bb.swJump2, %bb.swJump1
          br label %bb.loop1.head
        
        bb.loop1.head:                                    ; preds = %bb.swJump0, %bb.loop1.head
          %e1 = load volatile i1, ptr addrspace(1) %i, align 4
          br i1 %e1, label %bb.loop0.head, label %bb.loop1.head
        
        bb.swUnreachable:                        ; preds = %bb.sw
          unreachable
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC)
    # suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_TC('test_0')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
