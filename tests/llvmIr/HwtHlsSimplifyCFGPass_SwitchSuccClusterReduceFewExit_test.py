#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsSimplifyCFGPass_test import HwtHlsSimplifyCFGPass_TC


class HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return HwtHlsSimplifyCFGPass_TC._runTestOpt(self, llvm, *args, **kwargs)

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

    def test_SwitchSuccClusterReduceFewExit_2exit0(self):
        llvmIr = """\
        define void @test_SwitchSuccClusterReduceFewExit_2exit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          %st = alloca i2, align 1
          store i2 0, ptr %st, align 1
          br label %bb1
        
        bb1:                    ; preds = %bb8, %bb0
          %c0 = load i2, ptr %st, align 1
          %1 = load volatile i10, ptr addrspace(1) %i, align 2
          %c1 = load volatile i1, ptr addrspace(1) %i, align 2
          %v0 = load volatile i8, ptr addrspace(1) %i, align 2
          %v1 = load volatile i8, ptr addrspace(1) %i, align 2
          %c2 = icmp eq i8 %v0, 2
          switch i2 %c0, label %bb9 [
            i2 0, label %bb2
            i2 1, label %bb6.e0
          ]
        
        bb2:                                              ; preds = %bb1
          br i1 %c1, label %bb4, label %bb3
        
        bb3:                                     ; preds = %bb2, %bb6.e0
          br label %bb7.e1
        
        bb4:                          ; preds = %bb2
          br i1 %c2, label %bb5, label %bb6.e0
        
        bb5:                                ; preds = %bb4
          br label %bb7.e1
        
        bb6.e0:                                   ; preds = %bb1, %bb4
          %v2 = phi i8 [ %v1, %bb1 ], [ %v0, %bb4 ]
          store volatile i8 %v2, ptr addrspace(2) %o, align 1
          br label %bb3
        
        bb7.e1:          ; preds = %bb3, %bb5
          %v3 = phi i2 [ 1, %bb5 ], [ 0, %bb3 ]
          store i2 %v3, ptr %st, align 1
          br label %bb8
        
        bb8:                     ; preds = %bb7.e1
          br label %bb1
        
        bb9:                   ; preds = %bb1
          unreachable
        }
        """
        self._test_ll(llvmIr)

    
    def test_2exits_conditionInExit0(self):
        # :note: based on Axi4SParse2IfAndSequel_NO_FOOTER_16b_100MHz
        llvmIr = """\
        define void @test_2exits_conditionInExit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          br label %bb1
        

        bb1:                                             ; preds = %bb0, %bb.latch
          %swCond = phi i3 [ %swCond.phi, %bb.latch ], [ 0, %bb0 ]
          %c0 = load volatile i3, ptr addrspace(1) %i, align 4
          %c1 = load volatile i3, ptr addrspace(1) %i, align 4
          %c2 = icmp eq i3 %c1, 0
          switch i3 %c0, label %bb.def [
            i3 0, label %bb.c0
            i3 1, label %bb.latch
            i3 2, label %bb.c2
            i3 3, label %bb.c3
          ]
        
        bb.c0:                                              ; preds = %bb1
          br label %bb.latch

        bb.c2:                                              ; preds = %bb1
          store volatile i32 10, ptr addrspace(2) %o, align 4
          br i1 %c2, label %bb.latch, label %bb.c3
                
        bb.c3:                                             ; preds = %bb1, %bb.c2
          br label %bb.latch
        
        bb.latch:                                             ; preds = %bb.c0, %bb.c2, %bb1, %bb.c3
          %swCond.phi = phi i3 [ 2, %bb1 ], [ 0, %bb.c3 ], [ 3, %bb.c2 ], [ %c0, %bb.c0 ]
          store volatile i3 %swCond.phi, ptr addrspace(2) %o, align 4
          br label %bb1
        
        bb.def:                                             ; preds = %bb1
          unreachable
        }
        """
        self._test_ll(llvmIr, passKwArgs=dict(
            RunEarlyCSEPass=False,
            RunRomExtractPass=False,
            RunHwtHlsInstCombinePass=False,
            RunTrivialSimplifyCFGPass=False,
            RunSimplifyCFGPass=False,
            RunBitcountMergePass=False,
            )
        )


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC)
    # suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC('test_SwitchSuccClusterReduceFewExit_2exit0')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
