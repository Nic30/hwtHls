#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC

class PruneLoopPhiDeadIncomingValuesPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._testPruneLoopPhiDeadIncomingValuesPass()

    def test_ShiftSequential(self):
        # 0 in "9(d_sh)3" should be replaced with poison
        llvmIr0 = """
            define void @test_ShiftSequential(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
            bb0:
              br label %bb2
            
            bb2:
              %isChildLoop.bb3 = phi i1 [ false, %bb0 ], [ true, %bb3 ], [ false, %bb5.oldLatch ]
              %"9(d_sh)3" = phi i5 [ poison, %bb0 ], [ %"10", %bb3 ], [ 0, %bb5.oldLatch ]
              %"6(d_data)1511" = phi i14 [ undef, %bb0 ], [ %3, %bb3 ], [ %3, %bb5.oldLatch ]
              %0 = zext i14 %"6(d_data)1511" to i15
              br i1 %isChildLoop.bb3, label %bb3, label %bb2.split
            
            bb2.split:
              %dataIn0 = load volatile i21, ptr addrspace(1) %dataIn, align 4
              %1 = call i15 @hwtHls.bitRangeGet.i21.i6.i15.1(i21 %dataIn0, i6 1) #2
              %2 = call i5 @hwtHls.bitRangeGet.i21.i6.i5.16(i21 %dataIn0, i6 16) #2
              %"3" = icmp ne i5 %2, 0
              call void @llvm.assume(i1 %"3")
              br label %bb3
            
            bb3:
              %"6(d_data)12" = phi i15 [ %1, %bb2.split ], [ %0, %bb2 ]
              %"9(d_sh)" = phi i5 [ %2, %bb2.split ], [ %"9(d_sh)3", %bb2 ]
              %3 = call i14 @hwtHls.bitRangeGet.i15.i5.i14.1(i15 %"6(d_data)12", i5 1) #2
              %"10" = add i5 %"9(d_sh)", -1
              %"11.not" = icmp ne i5 %"10", 0
              br i1 %"11.not", label %bb2, label %bb5.oldLatch
            
            bb5.oldLatch:
              %4 = zext i15 %"6(d_data)12" to i16
              store volatile i16 %4, ptr addrspace(2) %dataOut, align 2
              br label %bb2
            }
        """
        self._test_ll(llvmIr0)

    
if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([LoopFlattenUsingIfPass_TC('test_whileWhile2xNested')])
    suite = testLoader.loadTestsFromTestCase(PruneLoopPhiDeadIncomingValuesPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
