#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function, verifyFunction, StringRef
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class HwtHlsSimplifyCFGPass_speculatePredecessor_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        # def printOnChange(ruleName: StringRef, F: Function):
        #     print("after ", ruleName.str())
        #     print(F)
        # 
        # llvm._dbgIrInstrCombineChangeCallbackFn = printOnChange
        # llvm._dbgIrCfgSimplifyChangeCallbackFn = printOnChange
        
        
        F = llvm._testHwtHlsSimplifyCFGPass(*args, **kwargs)
        assert not verifyFunction(F)
        return F


    def test_speculatePredecessor0(self):
        # note: based on HlsPythonHwrange_fromInt2
        llvmIr = """\
        define void @test_speculatePredecessor0(ptr addrspace(1) %o) {
        bb0:
          br label %bb.loop1.head

        bb.loop1.head:                                    ; preds = %bb0, %bb.loop0.latch
          %i0 = phi i3 [ %2, %bb.loop0.latch ], [ 0, %bb0 ]
          %i1 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i0, i3 0) #2
          br label %bb.loop2.head
        
        bb.loop2.head:                                    ; preds = %bb.loop2.head, %bb.loop1.head
          %i2 = phi i3 [ 0, %bb.loop1.head ], [ %1, %bb.loop2.head ]
          %i3 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i2, i3 0) #2
          %0 = call i8 @hwtHls.bitConcat.i2.i2.i4(i2 %i3, i2 %i1, i4 0) #2
          store volatile i8 %0, ptr addrspace(1) %o, align 1
          %1 = add i3 %i2, 1
          %hwrange.continue4.not = icmp eq i3 %1, -4
          %2 = add i3 %i0, 1
          %hwrange.continue.not.le.le = icmp eq i3 %2, -4
          br i1 %hwrange.continue4.not, label %bb.loop0.latch, label %bb.loop2.head
        
        bb.loop0.latch:                                   ; preds = %bb.loop2.head
          br label %bb.loop1.head
        }
        """
        self._test_ll(llvmIr)

    def test_speculatePredecessor1(self):
        # :note: based on HlsPythonHwrange_fromInt2
        # :note: test_speculatePredecessor0 in 1 additional loop
        llvmIr = """\
        define void @test_speculatePredecessor1(ptr addrspace(1) %o) {
        bb0:
          br label %bb.loop0.head
        
        bb.loop0.head:                                    ; preds = %bb.loop0.latch, %bb0
          br label %bb.loop1.head
        
        bb.loop1.head:                              ; preds = %bb.loop0.head, %bb.loop0.latch
          %i0 = phi i3 [ 0, %bb.loop0.head ], [ %2, %bb.loop0.latch ]
          %i1 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i0, i3 0) #2
          br label %bb.loop2.head
        
        bb.loop2.head:                        ; preds = %bb.loop2.head, %bb.loop1.head
          %i2 = phi i3 [ 0, %bb.loop1.head ], [ %1, %bb.loop2.head ]
          %i3 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i2, i3 0) #2
          %0 = call i8 @hwtHls.bitConcat.i2.i2.i4(i2 %i3, i2 %i1, i4 0) #2
          store volatile i8 %0, ptr addrspace(1) %o, align 1
          %1 = add i3 %i2, 1
          %hwrange.continue4.not = icmp eq i3 %1, -4
          %2 = add i3 %i0, 1
          %hwrange.continue.not.le.le = icmp eq i3 %2, -4
          br i1 %hwrange.continue4.not, label %bb.loop0.latch, label %bb.loop2.head
        
        bb.loop0.latch:                        ; preds = %bb.loop2.head
          br i1 %hwrange.continue.not.le.le, label %bb.loop0.head, label %bb.loop1.head
        }
        """
        self._test_ll(llvmIr)

    def test_speculatePredecessor2(self):
        # :note: based on HlsPythonHwrange_fromInt1_breakBefore
        llvmIr = """\
        define void @HlsPythonHwrange_fromInt1_breakBefore.mainThread(ptr addrspace(1) %o) {
        bb0:
          br label %bb.loop0.head
        
        bb.loop0.head:                              ; preds = %bb.loop0.latch, %bb0
          %i0 = phi i4 [ 0, %bb0 ], [ %i0.be, %bb.loop0.latch ]
          %0 = icmp eq i4 %i0, 4
          %1 = zext i4 %i0 to i8
          br i1 %0, label %bb2, label %bb1
        
        bb1:                              ; preds = %bb.loop0.head
          store volatile i8 %1, ptr addrspace(1) %o, align 1
          %2 = add nuw i4 %i0, 1
          %hwrange.continue = icmp ne i4 %2, -8
          br i1 %hwrange.continue, label %bb.loop0.latch, label %bb2
        
        bb2:                                   ; preds = %bb.loop0.head, %bb1
          br label %bb.loop0.latch
          
        bb.loop0.latch:                     ; preds = %bb1, %bb2
          %i0.be = phi i4 [ 0, %bb2 ], [ %2, %bb1 ]
          br label %bb.loop0.head
        }
        """
        self._test_ll(llvmIr)

    def test_speculatePredecessor3(self):
        llvmIr = """\
        define void @test_speculatePredecessor3(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          br label %bb27
        
        bb27:                                             ; preds = %bb45, %bb0
          %i_read3.r0.eof.reg2mem.0.reg2mem.0 = phi i1 [ %i_read3.r0.eof.reg2mem.1.ph.1lane, %bb45 ], [ undef, %bb0 ]
          %0 = load volatile i38, ptr addrspace(1) %i, align 8
          %1 = trunc i38 %0 to i1
          %2 = trunc i38 %0 to i16
          br i1 %1, label %bb32, label %bb44
        
        bb31:                                             ; preds = %bb44
          br i1 %1, label %bb33, label %bb45
        
        bb32:                                             ; preds = %bb27
          br label %bb44
        
        bb33:                                             ; preds = %bb31
          switch i16 %2, label %bb45 [
            i16 3, label %bb45
            i16 4, label %bb43
          ]
        
        bb43:                                             ; preds = %bb33
          br label %bb45
        
        bb44:                                             ; preds = %bb32, %bb27
          %.sink.0lane = phi i3 [ -4, %bb32 ], [ 0, %bb27 ]
          switch i3 %.sink.0lane, label %bb25 [
            i3 0, label %bb31
            i3 1, label %bb45
            i3 2, label %bb45
            i3 3, label %bb45
            i3 -4, label %bb45
          ]
        
        bb45:                                             ; preds = %bb44, %bb44, %bb44, %bb33, %bb44, %bb43, %bb33, %bb31
          %i_read3.r0.eof.reg2mem.1.ph.1lane = phi i1 [ false, %bb44 ], [ false, %bb44 ], [ false, %bb44 ], [ false, %bb33 ], [ false, %bb44 ], [ false, %bb43 ], [ false, %bb33 ], [ false, %bb31 ]
          br label %bb27
        
        bb25:                                             ; preds = %bb44
          unreachable
        }
        """
        self._test_ll(llvmIr, passKwArgs=dict(
            ForwardSwitchCondToPhi      = False,
            ConvertSwitchRangeToICmp    = False,
            ConvertSwitchToLookupTable  = False,
            NeedCanonicalLoops          = False,
            HoistCommonInsts            = False,
            SinkCommonInsts             = False,
            SimplifyCondBranch          = False,
            HoistCheapInsts             = False,
            RunEarlyCSEPass             = False,
            RunRomExtractPass           = False,
            RunHwtHlsInstCombinePass    = False,
            RunTrivialSimplifyCFGPass   = False,
            RunSimplifyCFGPass          = False,
            RunBitcountMergePass        = False,
        ))


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_speculatePredecessor_TC)
    # suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_speculatePredecessor_TC('test_speculatePredecessor3')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
