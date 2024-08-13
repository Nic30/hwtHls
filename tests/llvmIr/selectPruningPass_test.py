#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class SelectPruningPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._testSelectPruningPass()

    def test_nestedSelWithSameCond0(self):
        llvmIr0 = """
        define void @test_nestedSelWithSameCond0(ptr addrspace(1) %c, ptr addrspace(2) %v1, ptr addrspace(3) %o) {
          entry:
            br label %body
          
          body:
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            %s0.v1 = load volatile i2, ptr addrspace(2) %v1, align 1
            %s0 = select i1 %c0, i2 0, i2 %s0.v1
            %c0.not = xor i1 %c0, true
            %s1.v0 = call i4 @hwtHls.bitConcat.i1.i2.i1(i1 %c0.not, i2 1, i1 %c0) #2
            %s1.v1.1 = load volatile i1, ptr addrspace(1) %c, align 1
            %s1.v1 = call i4 @hwtHls.bitConcat.i2.i1.i1(i2 %s0, i1 true, i1 %s1.v1.1) #2
            %s1 = select i1 %c0, i4 %s1.v0, i4 %s1.v1
            store volatile i4 %s1, ptr addrspace(3) %o, align 1
            ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_nestedSelWithSameCond1(self):
        # originally Axi4SPacketCopyByteByByteHs.mainThread
        llvmIr0 = """
        define void @test_nestedSelWithSameCond1(ptr addrspace(1) %rx, ptr addrspace(2) %txBody) {
        entry:
          br label %blockL44i0_L88i0_88
        
        blockL44i0_L88i0_88:                              ; preds = %rxoff0, %entry
          %rxDataOffset.011 = phi i1 [ false, %entry ], [ %spec.select1017, %rxoff0 ]
          %rxDataLast.1 = phi i1 [ undef, %entry ], [ %rxDataLast.2, %rxoff0 ]
          %rxDataMask.112 = phi i1 [ undef, %entry ], [ %rxDataMask.214, %rxoff0 ]
          %rxData.1 = phi i16 [ undef, %entry ], [ %rxData.2, %rxoff0 ]
          %"(readEn)13" = icmp eq i1 %rxDataOffset.011, false
          br i1 %"(readEn)13", label %0, label %rxoff0
        
        0:                                                ; preds = %blockL44i0_L88i0_88
          %"rx1(rx_read).opt" = load volatile i19, ptr addrspace(1) %rx, align 4
          %1 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %"rx1(rx_read).opt", i6 0) #2
          %2 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %"rx1(rx_read).opt", i6 18) #2
          %3 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %"rx1(rx_read).opt", i6 17) #2
          br label %rxoff0
        
        rxoff0:                                           ; preds = %blockL44i0_L88i0_88, %0
          %rxDataLast.2 = phi i1 [ %2, %0 ], [ %rxDataLast.1, %blockL44i0_L88i0_88 ]
          %rxDataMask.214 = phi i1 [ %3, %0 ], [ %rxDataMask.112, %blockL44i0_L88i0_88 ]
          %rxData.2 = phi i16 [ %1, %0 ], [ %rxData.1, %blockL44i0_L88i0_88 ]
          %4 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %rxData.2, i5 0) #2
          %5 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %rxData.2, i5 8) #2
          %6 = xor i1 %rxDataMask.214, true
          %7 = and i1 %rxDataLast.2, %6
          %8 = xor i1 %7, true
          %9 = call i9 @hwtHls.bitConcat.i8.i1(i8 %4, i1 %7) #2
          %10 = call i9 @hwtHls.bitConcat.i8.i1(i8 %5, i1 %rxDataLast.2) #2
          %spec.select815 = select i1 %"(readEn)13", i9 %9, i9 %10
          %11 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %spec.select815, i5 8) #2
          %12 = call i8 @hwtHls.bitRangeGet.i9.i5.i8.0(i9 %spec.select815, i5 0) #2
          %spec.select916 = select i1 %"(readEn)13", i1 %8, i1 false
          store volatile i8 %12, ptr addrspace(2) %txBody, align 1
          %spec.select1017 = select i1 %11, i1 false, i1 %spec.select916
          br label %blockL44i0_L88i0_88
        }
        """
        self._test_ll(llvmIr0)

    def test_sameAndWithCond(self):
        llvmIr0 = """
        define void @test_sameAndWithCond(ptr addrspace(1) %c,ptr addrspace(2) %v0a, ptr addrspace(3) %v1a, ptr addrspace(4) %v2a,  ptr addrspace(5) %o) {
          entry:
            br label %body
          
          body:
            %c0 = load volatile i1, ptr addrspace(1) %c, align 1
            %v0 = load volatile i1, ptr addrspace(2) %v0a, align 1
            %v1 = load volatile i1, ptr addrspace(3) %v1a, align 1
            %v2 = load volatile i1, ptr addrspace(4) %v2a, align 1
            %v3 = and i1 %c0, %v0
            %s0.v0 = and i1 %v1, %v3 ; = and %v1, %v0 
            %s0.v1 = and i1 %v2, %v3 ; = i0 0
            %s0 = select i1 %c0, i1 %s0.v0, i1 %s0.v1 ; = and %c0, %s0.v0
            store volatile i1 %s0, ptr addrspace(5) %o, align 1
            ret void
        }
        """
        self._test_ll(llvmIr0)


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SelectPruningPass_TC('test_sameAndWithCond')])
    suite = testLoader.loadTestsFromTestCase(SelectPruningPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
