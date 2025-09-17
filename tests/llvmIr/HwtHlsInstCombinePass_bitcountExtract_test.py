#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsInstCombinePass_test import HwtHlsInstCombinePass_TC


class HwtHlsInstCombinePass_bitcountExtract_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, runBitcountMergePass=True, runStreamReadEoFThreading=False) -> Function:
        return HwtHlsInstCombinePass_TC._runTestOpt(self, llvm,
                                                    runBitcountMergePass=runBitcountMergePass, runStreamReadEoFThreading=runStreamReadEoFThreading)

    def test_tryReduceSelectInst_deepAdderChainToBitCounts0(self):
        llvmIr = """\
        define void @test_tryReduceSelectInst_deepAdderChainToBitCounts0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
        bb.0:
          %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
          %c0 = load volatile i1, ptr addrspace(2) %condIn, align 1
          %c1 = load volatile i1, ptr addrspace(2) %condIn, align 1
          %c2 = load volatile i1, ptr addrspace(2) %condIn, align 1
          %c3 = load volatile i1, ptr addrspace(2) %condIn, align 1
        
          %v1 = add i9 %v0, 1
          %v2 = select i1 %c0, i9 %v0, i9 %v1
          %v3 = add i9 %v2, 1
          %v4 = select i1 %c1, i9 %v2, i9 %v3
          %v5 = add i9 %v4, 1
          %v6 = select i1 %c2, i9 %v4, i9 %v5
          %v7 = add i9 %v6, 1
          %v8 = select i1 %c3, i9 %v6, i9 %v7
          store volatile i9 %v8, ptr addrspace(3) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_ctpop_0(self):
        llvmIr = """\
        define void @test_ctpop_0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %bb1
        bb1:
          %acc = phi i8 [ 0, %bb0 ], [ %acc.3, %bb1 ]
          %0 = load volatile i4, ptr addrspace(1) %rx, align 1
          %b0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %0, i3 0) #2
          %b1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %0, i3 1) #2
          %b2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.2(i4 %0, i3 2) #2
          %b3 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %0, i3 3) #2
          %acc.0.add = add i8 %acc, 1
          %acc.0 = select i1 %b0, i8 %acc.0.add, i8 %acc
          %acc.1.add = add i8 %acc.0, 1
          %acc.1 = select i1 %b1, i8 %acc.1.add, i8 %acc.0
          %acc.2.add = add i8 %acc.1, 1
          %acc.2 = select i1 %b2, i8 %acc.2.add, i8 %acc.1
          %acc.3.add = add i8 %acc.2, 1
          %acc.3 = select i1 %b3, i8 %acc.3.add, i8 %acc.2
          store volatile i8 %acc.3, ptr addrspace(2) %tx, align 1
          br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_ctpop_withLimit(self):
        llvmIr = """\
        define void @test_ctpop_withLimit(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %bb1
        bb1:
          %acc = phi i8 [ 0, %bb0 ], [ %acc.3, %bb1 ]
          %0 = load volatile i4, ptr addrspace(1) %rx, align 1
          %b0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %0, i3 0) #2
          %b1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %0, i3 1) #2
          %b2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.2(i4 %0, i3 2) #2
          %b3 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %0, i3 3) #2
          %limit.0 = icmp ne i8 %acc, 10
          %c.0 = and i1 %b0, %limit.0
          %acc.0.add = add i8 %acc, 1
          %acc.0 = select i1 %c.0, i8 %acc.0.add, i8 %acc
          %limit.1 = icmp ne i8 %acc.0, 10
          %c.1 = and i1 %b1, %limit.1
          %acc.1.add = add i8 %acc.0, 1
          %acc.1 = select i1 %c.1, i8 %acc.1.add, i8 %acc.0
          %limit.2 = icmp ne i8 %acc.1, 10
          %c.2 = and i1 %b2, %limit.2
          %acc.2.add = add i8 %acc.1, 1
          %acc.2 = select i1 %c.2, i8 %acc.2.add, i8 %acc.1
          %limit.3 = icmp ne i8 %acc.2, 10
          %c.3 = and i1 %b3, %limit.3
          %acc.3.add = add i8 %acc.2, 1
          %acc.3 = select i1 %c.3, i8 %acc.3.add, i8 %acc.2
          store volatile i8 %acc.3, ptr addrspace(2) %tx, align 1
          br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_ctpop_withLimit_and_iremovableIntermediateUse(self):
        # this should generate 2* ctpop
        llvmIr = """\
        define void @test_ctpop_withLimit_and_iremovableIntermediateUse(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %bb1
        bb1:
          %acc = phi i8 [ 0, %bb0 ], [ %acc.3, %bb1 ]
          %0 = load volatile i4, ptr addrspace(1) %rx, align 1
          %b0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %0, i3 0) #2
          %b1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %0, i3 1) #2
          %b2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.2(i4 %0, i3 2) #2
          %b3 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %0, i3 3) #2
          %limit.0 = icmp ne i8 %acc, 10
          %c.0 = and i1 %b0, %limit.0
          %acc.0.add = add i8 %acc, 1
          %acc.0 = select i1 %c.0, i8 %acc.0.add, i8 %acc
          %limit.1 = icmp ne i8 %acc.0, 10
          %c.1 = and i1 %b1, %limit.1
          %acc.1.add = add i8 %acc.0, 1
          %acc.1 = select i1 %c.1, i8 %acc.1.add, i8 %acc.0
          %limit.2 = icmp ne i8 %acc.1, 10
          %c.2 = and i1 %b2, %limit.2
          %acc.2.add = add i8 %acc.1, 1
          %acc.2 = select i1 %c.2, i8 %acc.2.add, i8 %acc.1
          %c.3.intermediate = icmp ne i8 %acc.2, 5
          %limit.3 = icmp ne i8 %acc.2, 10
          %c.3 = and i1 %b3, %limit.3
          %acc.3.add = add i8 %acc.2, 1
          %acc.3 = select i1 %c.3, i8 %acc.3.add, i8 %acc.2
          store volatile i8 %acc.3, ptr addrspace(2) %tx, align 1
          store volatile i1 %c.3.intermediate, ptr addrspace(2) %tx, align 1
          br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_cttz_withIntermediateUse(self):
        llvmIr = """\
        define void @test_cttz_withIntermediateUse(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %loop.pkt
        
        loop.pkt:
          br label %loop.pkt.read
        
        loop.pkt.read:
          %curLen.0.in = phi i2 [ 0, %loop.pkt ], [ %curLen.2.out, %bb.w.exit ]
          %0 = load volatile i4, ptr addrspace(1) %rx, align 1
          %strb = call i3 @hwtHls.bitRangeGet.i4.i3.i3.0(i4 %0, i3 0) #2
          %strb0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %0, i3 0) #2
          %strb1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %0, i3 1) #2
          %strb2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.2(i4 %0, i3 2) #2
          %last = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %0, i3 3) #2
          %prevMaskBit1Impl = icmp ule i1 %strb1, %strb0
          call void @llvm.assume(i1 %prevMaskBit1Impl)
          %maskBitNonLastImpl = or i1 %last, %strb1
          call void @llvm.assume(i1 %maskBitNonLastImpl)
          %prevMaskBit1Impl33 = icmp ule i1 %strb2, %strb1
          call void @llvm.assume(i1 %prevMaskBit1Impl33)
          %maskBitNonLastImpl34 = or i1 %last, %strb2
          call void @llvm.assume(i1 %maskBitNonLastImpl34)
          %7 = icmp eq i3 %strb, -1
          %maskAll1ifLastImpl = or i1 %last, %7
          call void @llvm.assume(i1 %maskAll1ifLastImpl)
          %strb1.n = xor i1 %strb1, true
          %9 = and i1 %last, %strb1.n
          %limit.0 = icmp ne i2 %curLen.0.in, 1
          %wEn.0 = and i1 %strb0, %limit.0
          %13 = add i2 %curLen.0.in, 1
          %curLen.1.in = select i1 %wEn.0, i2 %13, i2 %curLen.0.in
          %strb2.n = xor i1 %strb2, true
          %15 = and i1 %last, %strb2.n
          %limit.1 = icmp ne i2 %curLen.1.in, 1
          %wEn.1 = and i1 %strb1, %limit.1
          %19 = add i2 %curLen.1.in, 1
          %curLen.2.in = select i1 %wEn.1, i2 %19, i2 %curLen.1.in
          %limit.2 = icmp ne i2 %curLen.2.in, 1
          %wEn.0.2 = and i1 %strb2, %limit.2
          %23 = add i2 %curLen.2.in, 1
          %curLen.2.out = select i1 %wEn.0.2, i2 %23, i2 %curLen.2.in
          %24 = xor i1 %9, true
          %25 = xor i1 %15, true
          %26 = and i1 %24, %25
          %wEn.2 = and i1 %26, %wEn.0.2
          %27 = or i1 %wEn.0, %wEn.1
          %wEn.any = or i1 %27, %wEn.2
          %29 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %wEn.0, i1 %wEn.1, i1 %wEn.2) #2
          br i1 %wEn.any, label %bb.w, label %bb.w.exit
        
        bb.w:
          store volatile i3 %29, ptr addrspace(2) %tx, align 2
          br label %bb.w.exit
        
        bb.w.exit:
          br i1 %last, label %loop.pkt.eof, label %loop.pkt.read
        
        loop.pkt.eof:
          br label %loop.pkt
        }
        """
        self._test_ll(llvmIr, passKwArgs=dict(runBitcountMergePass=True))


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HwtHlsInstCombinePass_bitcountExtract_TC('test_cttz_withIntermediateUse')])
    suite = testLoader.loadTestsFromTestCase(HwtHlsInstCombinePass_bitcountExtract_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
