#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class SimplifyCFG2Pass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return llvm._testSimplifyCFG2Pass(*args, **kwargs)

    def test_loadMerge(self):
        llvmIr = """\
        define void @loadMerge(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        loadMerge:
          br label %bb0_sw
        
        bb0_sw:
          %i0.w0 = load volatile i17, ptr addrspace(1) %i, align 4
          %0 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i0.w0, i6 0) #2
          %1 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i0.w0, i6 16) #2
          %i0 = call i17 @hwtHls.bitConcat.i16.i1(i16 %0, i1 %1) #2
          %2 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i0, i6 0) #2
          switch i16 %2, label %bb0_sw_def [
            i16 3, label %bb0_sw_case3
            i16 4, label %bb0_sw_case4
          ]
        
        bb0_sw_case3:
          %i1.w0 = load volatile i17, ptr addrspace(1) %i, align 4
          %3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i1.w0, i6 0) #2
          %4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i1.w0, i6 16) #2
          %i1.w1 = load volatile i17, ptr addrspace(1) %i, align 4
          %5 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %i1.w1, i6 0) #2
          %6 = call i24 @hwtHls.bitConcat.i16.i8(i16 %3, i8 %5) #2
          %i1 = call i25 @hwtHls.bitConcat.i24.i1(i24 %6, i1 %4) #2
          %7 = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %i1, i6 0) #2
          %8 = zext i24 %7 to i32
          store volatile i32 %8, ptr addrspace(2) %o, align 4
          br label %bb0_sw_def
        
        bb0_sw_def:
          %iDataOffset.1 = phi i1 [ true, %bb0_sw ], [ true, %bb0_sw_case4 ], [ %4, %bb0_sw_case3 ]
          br i1 %iDataOffset.1, label %bb_opt_ld, label %ioff0
        
        bb_opt_ld:
          %i3.opt = load volatile i17, ptr addrspace(1) %i, align 4
          br label %ioff0
        
        ioff0:
          br label %bb0_sw
        
        bb0_sw_case4:
          %i2.w0 = load volatile i17, ptr addrspace(1) %i, align 4
          %9 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i2.w0, i6 0) #2
          %10 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i2.w0, i6 16) #2
          %i2.w1 = load volatile i17, ptr addrspace(1) %i, align 4
          %11 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i2.w1, i6 0) #2
          %12 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i2.w1, i6 16) #2
          %13 = call i32 @hwtHls.bitConcat.i16.i16(i16 %9, i16 %11) #2
          %14 = or i1 %10, %12
          %i3 = call i33 @hwtHls.bitConcat.i32.i1(i32 %13, i1 %14) #2
          %15 = call i32 @hwtHls.bitRangeGet.i33.i7.i32.0(i33 %i3, i7 0) #2
          store volatile i32 %15, ptr addrspace(2) %o, align 4
          br label %bb0_sw_def
        }
        """
        self._test_ll(llvmIr, passKwArgs=dict(
                          ForwardSwitchCondToPhi = True,
                          ConvertSwitchRangeToICmp = True,
                          NeedCanonicalLoops = False,
                          HoistCommonInsts = True,
                          SinkCommonInsts = True,
                          HoistCheapInsts = True
                      ))

    def test_optionalStore0(self):
        llvmIr = """\
        define void @optionalStore0(ptr addrspace(1) %o) {
        entry:
          br label %bb0
        
        bb0:
          %i = phi i1 [ false, %entry ], [ %"i.not", %bb2 ]
          store volatile i8 1, ptr addrspace(1) %o, align 1
          br i1 %i, label %bb2, label %bb1
        
        bb1: 
          store volatile i8 2, ptr addrspace(1) %o, align 1
          br label %bb2
        
        bb2:
          %"i.not" = xor i1 %i, true
          store volatile i8 3, ptr addrspace(1) %o, align 1
          br label %bb0
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SimplifyCFG2Pass_TC('test_loadMerge')])
    suite = testLoader.loadTestsFromTestCase(SimplifyCFG2Pass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
