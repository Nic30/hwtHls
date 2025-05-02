#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class HwtHlsInstCombinePass_streamEoFThreading_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, runBitcountMergePass=False, runStreamReadEoFThreading=False) -> Function:
        return llvm._testHwtHlsInstCombinePass(runBitcountMergePass, runStreamReadEoFThreading)

    def test_streamEoFThreading0(self):
        llvmIr = """\
        define void @test_streamEoFThreading0(ptr addrspace(1) %o, ptr addrspace(2) %i) !hwtHls.streamIo !8 {
        bb0:
          br label %bb1
        
        bb1:
          %.w0 = load volatile i37, ptr addrspace(2) %i, align 8
          %0 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.w0, i7 33) #2
          %eof = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.w0, i7 36) #2
          %1 = xor i1 %0, true
          %2 = and i1 %eof, %1
          store volatile i1 %1, ptr addrspace(1) %o, align 4
          store volatile i1 %2, ptr addrspace(1) %o, align 4
          br i1 %eof, label %bb2, label %bb1
        
        bb2:
          store volatile i8 10, ptr addrspace(1) %o, align 4
          br label %bb1
        }
        
        !8 = !{!9}
        !9 = !{i32 1, i32 0, i32 32, i32 8, !"mask", i32 0, !"eof", i32 0, i32 1}
        """
        self._test_ll(llvmIr, passKwArgs=dict(runStreamReadEoFThreading=True))


    def test_streamEoFThreading1(self):
        # test_streamEoFThreading0 with assume added
        llvmIr = """\
        define void @test_streamEoFThreading1(ptr addrspace(1) %o, ptr addrspace(2) %i) !hwtHls.streamIo !8 {
        bb0:
          br label %bb1
        
        bb1:
          %.w0 = load volatile i37, ptr addrspace(2) %i, align 8
          %0 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.w0, i7 33) #2
          %eof = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.w0, i7 36) #2
          %2 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %.w0, i7 32) #2
          %5 = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %.w0, i7 32) #2
          %prevMaskBit1Impl8 = icmp ule i1 %0, %2
          call void @llvm.assume(i1 %prevMaskBit1Impl8)
          %9 = icmp eq i4 %5, -1
          %maskAll1IfNonLastImpl16 = or i1 %eof, %9
          call void @llvm.assume(i1 %maskAll1IfNonLastImpl16)
          %10 = xor i1 %0, true
          %11 = and i1 %eof, %10
          store volatile i1 %11, ptr addrspace(1) %o, align 4
          br i1 %eof, label %bb2, label %bb1
        
        bb2:
          store volatile i8 10, ptr addrspace(1) %o, align 4
          br label %bb1
        }
        
        !8 = !{!9}
        !9 = !{i32 1, i32 0, i32 32, i32 8, !"mask", i32 0, !"eof", i32 0, i32 1}
        """
        self._test_ll(llvmIr, passKwArgs=dict(runStreamReadEoFThreading=True))

    def test_streamEoFThreading2(self):
        llvmIr = """\
        define void @test_streamEoFThreading2(ptr addrspace(1) %o, ptr addrspace(2) %i) !hwtHls.streamIo !8 {
        bb0:
          br label %bb1
        
        bb1:
          br label %bb2
        
        bb2:
          br label %bb3
        
        bb3:
          %r = load volatile i19, ptr addrspace(2) %i, align 4
          %r.eof = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %r, i6 18) #2
          %r.m0 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %r, i6 16) #2
          %r.m1 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %r, i6 17) #2
          %3 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.16(i19 %r, i6 16) #2
          %4 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.17(i19 %r, i6 17) #2
          ; %NonEoFImplMaskBit117 = icmp ne i2 %4, 0
          ; call void @llvm.assume(i1 %NonEoFImplMaskBit117)
          ; %6 = icmp eq i2 %3, -1
          ; %NonEoFImplMaskAll118 = or i1 %r.eof, %6
          ; call void @llvm.assume(i1 %NonEoFImplMaskAll118)
          ; %prevMaskBit1Impl = icmp ule i1 %r.m1, %r.m0
          ; call void @llvm.assume(i1 %prevMaskBit1Impl)
          %7 = xor i1 %r.m1, true
          %8 = and i1 %r.eof, %7
          %.1 = and i1 %r.m0, %8
          %.2 = and i1 %r.m1, %r.eof
          %9 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %r.m1) #2
          %10 = or i1 %.1, %.2
          br i1 %r.m0, label %bb4.write, label %bb5.exit
        
        bb4.write:
          store volatile i2 %9, ptr addrspace(1) %o, align 4
          store volatile i1 %10, ptr addrspace(1) %o, align 4
          br label %bb5.exit
        
        bb5.exit:
          br i1 %r.eof, label %bb6.eof, label %bb3
        
        bb6.eof:
          br label %bb2
        }

        !8 = !{!9}
        !9 = !{i32 1, i32 0, i32 16, i32 8, !"mask", i32 0, !"eof", i32 0, i32 1}
        """
        self._test_ll(llvmIr, passKwArgs=dict(runStreamReadEoFThreading=True))


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HwtHlsInstCombinePass_streamEoFThreading_TC('test_streamEoFThreading2')])
    suite = testLoader.loadTestsFromTestCase(HwtHlsInstCombinePass_streamEoFThreading_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
