from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.HwtHlsSimplifyCFGPass_test import HwtHlsSimplifyCFGPass_TC


class HwtHlsSimplifyCFGPass_phiToLogicalExp_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return HwtHlsSimplifyCFGPass_TC._runTestOpt(self, llvm, *args, **kwargs)

    def test_phiToLogicalExp0(self):
        llvmIr = """\
        define void @test_phiToLogicalExp0(ptr addrspace(1) %cIn, ptr addrspace(2) %out) {
        bb.entry:
          br label %bb0.guard

        bb0.guard:
          %bb0.g.c = load volatile i1, ptr addrspace(1) %cIn, align 1
          %bb0.e.c = load volatile i1, ptr addrspace(1) %cIn, align 1
          %bb1.g.c = load volatile i1, ptr addrspace(1) %cIn, align 1
          %bb1.e.c = load volatile i1, ptr addrspace(1) %cIn, align 1
          %bb2.g.c = load volatile i1, ptr addrspace(1) %cIn, align 1
          %bb2.e.c = load volatile i1, ptr addrspace(1) %cIn, align 1
          br i1 %bb0.g.c, label %bb0.enabled, label %bb0.exit
        
        bb0.enabled:
          br label %bb0.exit
        
        bb0.exit:
          %bb0.en.0 = phi i1 [ true, %bb0.enabled ], [ false, %bb0.guard ]
          br i1 %bb0.e.c, label %bb.preexit, label %bb1.guard
        
        bb1.guard:
          br i1 %bb1.g.c, label %bb1.enabled, label %bb1.exit
        
        bb1.enabled:
          br label %bb1.exit
        
        bb1.exit:
          %bb1.en.0 = phi i1 [ true, %bb1.enabled ], [ false, %bb1.guard ]
          br i1 %bb1.e.c, label %bb.preexit, label %bb2.guard
        
        bb2.guard:
          br i1 %bb2.g.c, label %bb2.enabled, label %bb2.exit
        
        bb2.enabled:
          br label %bb2.exit
        
        bb2.exit:
          %bb2.en.0 = phi i1 [ true, %bb2.enabled ], [ false, %bb2.guard ]
          br i1 %bb2.e.c, label %bb.preexit, label %bb.exit
        
        bb.preexit:
          %bb1.en.1 = phi i1 [ false, %bb0.exit ], [ %bb1.en.0, %bb1.exit ], [ %bb1.en.0, %bb2.exit ]
          %bb2.en.1 = phi i1 [ false, %bb0.exit ], [ false, %bb1.exit ], [ %bb2.en.0, %bb2.exit ]
          br label %bb.exit
        
        bb.exit:
          %bb1.en.2 = phi i1 [ %bb1.en.1, %bb.preexit ], [ %bb1.en.0, %bb2.exit ]
          %bb2.en.2 = phi i1 [ %bb2.en.1, %bb.preexit ], [ %bb2.en.0, %bb2.exit ]
          store volatile i1 %bb0.en.0, ptr addrspace(2) %out, align 1
          store volatile i1 %bb1.en.2, ptr addrspace(2) %out, align 1
          store volatile i1 %bb2.en.2, ptr addrspace(2) %out, align 1
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_phiToLogicalExp1(self):
        llvmIr = """\
        define void @test_phiToLogicalExp1(ptr addrspace(1) %rx, ptr addrspace(2) %out) {
        bb.0:
          %.r0 = load volatile i37, ptr addrspace(1) %rx, align 8
          %0 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.r0, i7 33) #2
          %.eof51 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.r0, i7 36) #2
          %1 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %.r0, i7 32) #2
          %2 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.34(i37 %.r0, i7 34) #2
          %3 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %.r0, i7 35) #2
          %.mask52 = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %.r0, i7 32) #2
          %4 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.0(i37 %.r0, i7 0) #2
          %5 = call i2 @hwtHls.bitRangeGet.i37.i7.i2.35(i37 %.r0, i7 35) #2
          %6 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.24(i37 %.r0, i7 24) #2
          %7 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.16(i37 %.r0, i7 16) #2
          %8 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.8(i37 %.r0, i7 8) #2
          %.mask = call i3 @hwtHls.bitRangeGet.i37.i7.i3.33(i37 %.r0, i7 33) #2
          %prevMaskBit1Impl62 = icmp ule i1 %0, %1
          call void @llvm.assume(i1 %prevMaskBit1Impl62)
          %NonEoFImplMaskBit1 = or i1 %.eof51, %0
          call void @llvm.assume(i1 %NonEoFImplMaskBit1)
          %prevMaskBit1Impl63 = icmp ule i1 %2, %0
          call void @llvm.assume(i1 %prevMaskBit1Impl63)
          %prevMaskBit1Impl64 = icmp ule i1 %2, %1
          call void @llvm.assume(i1 %prevMaskBit1Impl64)
          %NonEoFImplMaskBit165 = or i1 %.eof51, %2
          call void @llvm.assume(i1 %NonEoFImplMaskBit165)
          %prevMaskBit1Impl66 = icmp ule i1 %3, %2
          call void @llvm.assume(i1 %prevMaskBit1Impl66)
          %prevMaskBit1Impl67 = icmp ule i1 %3, %1
          call void @llvm.assume(i1 %prevMaskBit1Impl67)
          %NonEoFImplMaskBit168 = icmp ne i2 %5, 0
          call void @llvm.assume(i1 %NonEoFImplMaskBit168)
          %9 = icmp eq i4 %.mask52, -1
          %NonEoFImplMaskAll169 = or i1 %.eof51, %9
          call void @llvm.assume(i1 %NonEoFImplMaskAll169)
          %10 = xor i1 %0, true
          %11 = and i1 %.eof51, %10
          %spec.select41 = and i1 %1, %11
          %12 = icmp eq i3 %.mask, -1
          %NonEoFImplMaskAll1 = or i1 %.eof51, %12
          %prevMaskBit1Impl38 = icmp ule i1 %3, %0
          %13 = xor i1 %2, true
          %14 = and i1 %.eof51, %13
          %15 = xor i1 %3, true
          %16 = and i1 %.eof51, %15
          %.017 = and i1 %0, %14
          %.023 = and i1 %2, %16
          %.029 = and i1 %3, %.eof51
          br i1 %11, label %bb.sink, label %bb.1
        
        bb.1:                                    ; preds = %bb.0
          call void @llvm.assume(i1 %NonEoFImplMaskAll1)
          call void @llvm.assume(i1 %prevMaskBit1Impl38)
          br i1 %14, label %bb.sink, label %bb.2
        
        bb.2:                                    ; preds = %bb.1
          br i1 %16, label %bb.sink, label %bb.3
        
        bb.3:                                    ; preds = %bb.2
          br label %bb.sink
        
        bb.sink:              ; preds = %bb.3, %bb.2, %bb.1, %bb.0
          %phi0 = phi i1 [ false, %bb.0 ], [ false, %bb.1 ], [ false, %bb.2 ], [ %3, %bb.3 ]
          %phi1 = phi i1 [ false, %bb.0 ], [ false, %bb.1 ], [ false, %bb.2 ], [ %.029, %bb.3 ]
          %phi2 = phi i1 [ false, %bb.0 ], [ false, %bb.1 ], [ %2, %bb.2 ], [ %2, %bb.3 ]
          %phi3 = phi i1 [ false, %bb.0 ], [ false, %bb.1 ], [ %.023, %bb.2 ], [ %.023, %bb.3 ]
          %phi4 = phi i1 [ false, %bb.0 ], [ %0, %bb.1 ], [ %0, %bb.2 ], [ %0, %bb.3 ]
          %phi5 = phi i1 [ false, %bb.0 ], [ %.017, %bb.1 ], [ %.017, %bb.2 ], [ %.017, %bb.3 ]
          %phi6 = phi i1 [ true, %bb.0 ], [ true, %bb.1 ], [ true, %bb.2 ], [ %.eof51, %bb.3 ]
          store volatile i1 %phi0, ptr addrspace(2) %out, align 1
          store volatile i1 %phi1, ptr addrspace(2) %out, align 1
          store volatile i1 %phi2, ptr addrspace(2) %out, align 1
          store volatile i1 %phi3, ptr addrspace(2) %out, align 1
          store volatile i1 %phi4, ptr addrspace(2) %out, align 1
          store volatile i1 %phi5, ptr addrspace(2) %out, align 1
          store volatile i1 %phi6, ptr addrspace(2) %out, align 1
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_phiToLogicalExp_just2UniqueValues(self):
        llvmIr = """\
        define void @test_phiToLogicalExp_just2UniqueValues(ptr addrspace(1) %cIn, ptr addrspace(2) %o) {
        bb0:
          br label %bb.L0.head
        
        bb.L0.head:                                  ; preds = %bb0, %bb.L0.latch
          br label %bb.L1.head
        
        bb.L1.head:                           ; preds = %bb.L1.latch, %bb.L0.head
          %c0 = load volatile i1, ptr addrspace(1) %cIn, align 1
          %c1 = load volatile i1, ptr addrspace(1) %cIn, align 1
          %c2 = load volatile i1, ptr addrspace(1) %cIn, align 1
          %c3 = load volatile i1, ptr addrspace(1) %cIn, align 1
          %v0 = load volatile i32, ptr addrspace(1) %cIn, align 1
          %v1 = load volatile i32, ptr addrspace(1) %cIn, align 1
          br i1 %c0, label %bb.L0.latch, label %bb.L1.1
        
        bb.L1.1:                         ; preds = %bb.L1.head
          br i1 %c1, label %bb.L0.latch, label %bb.L1.2
        
        bb.L1.2:                         ; preds = %bb.L1.1
          br i1 %c2, label %bb.L0.latch, label %bb.L1.latch
        
        bb.L1.latch:                         ; preds = %bb.L1.2
          br i1 %c3, label %bb.L0.latch, label %bb.L1.head
        
        bb.L0.latch:                                  ; preds = %bb.L1.latch, %bb.L1.2, %bb.L1.1, %bb.L1.head
          %res = phi i32 [ %v0, %bb.L1.head ], [ %v0, %bb.L1.1 ], [ %v1, %bb.L1.2 ], [ %v1, %bb.L1.latch ]
          store volatile i32 %res, ptr addrspace(2) %o, align 4
          br label %bb.L0.head
        }
        """
        self._test_ll(llvmIr, use_generateAndAppendHwtHlsFunctionDeclarations=False)



if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_phiToLogicalExp_TC)
    suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_phiToLogicalExp_TC('test_phiToLogicalExp_just2UniqueValues')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
