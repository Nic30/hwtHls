#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.bitWidthReduction_test import BitwidthReductionPass_TC


class BitwidthReductionPass_PHI_inLoopHeader_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return BitwidthReductionPass_TC._runTestOpt(self, llvm)

    def test_loopCondBitSet(self):
        llvmIr = """\
        define void @LoopCondBitSet(ptr addrspace(1) %i, ptr addrspace(2) %o) {
            bb0:
              br label %bb1
            
            bb1:
              %.phiConc33 = phi i4 [ -8, %bb0 ], [ %11, %bb1 ]
              %.phiConc = phi i4 [ 0, %bb0 ], [ %10, %bb1 ]
              %0 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.1(i4 %.phiConc33, i3 1) #2
              %1 = call i3 @hwtHls.bitRangeGet.i4.i3.i3.1(i4 %.phiConc33, i3 1) #2
              %2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %.phiConc33, i3 3) #2
              %"i0(i_read)" = load volatile i1, ptr addrspace(1) %i, align 1
              %.opConc = select i1 %"i0(i_read)", i4 %.phiConc33, i4 0
              %.opConc34 = or i4 %.phiConc, %.opConc
              %3 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.0(i4 %.opConc34, i3 0) #2
              %4 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4 %.opConc34, i3 2) #2
              store volatile i4 %.opConc34, ptr addrspace(2) %o, align 1
              %"9.not32" = icmp ne i3 %1, 0
              %5 = select i1 %"9.not32", i2 %4, i2 0
              %".10(qMask)5" = and i1 %2, %"9.not32"
              %6 = call i4 @hwtHls.bitConcat.i2.i2(i2 %3, i2 %0) #2
              %7 = select i1 %"9.not32", i4 %6, i4 0
              %8 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.0(i4 %7, i3 0) #2
              %9 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4 %7, i3 2) #2
              %"9.not" = icmp eq i3 %1, 0
              %10 = call i4 @hwtHls.bitConcat.i2.i2(i2 %8, i2 %5) #2
              %11 = call i4 @hwtHls.bitConcat.i2.i1.i1(i2 %9, i1 %".10(qMask)5", i1 %"9.not") #2
              br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_PhiChain0(self):
        # :see: PyArrShift
        llvmIr = """\
        define void @PhiChain0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
         bb0:
           br label %bb1
         
         bb1:
           %arr0 = phi i8 [ 0, %bb0 ], [ %i_read, %bb1 ]
           %arr1 = phi i8 [ 0, %bb0 ], [ %arr0, %bb1 ]
           %i_read = load volatile i8, ptr addrspace(1) %i, align 1
           store volatile i8 %arr1, ptr addrspace(2) %o, align 1
           br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_PhiChain1(self):
        # :see: PyArrShift, same as test_PhiChain0 just with undef instead 0
        llvmIr = """\
        define void @PhiChain1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
         bb0:
           br label %bb1
         
         bb1:
           %arr0 = phi i8 [ undef, %bb0 ], [ %i_read, %bb1 ]
           %arr1 = phi i8 [ undef, %bb0 ], [ %arr0, %bb1 ]
           %i_read = load volatile i8, ptr addrspace(1) %i, align 1
           store volatile i8 %arr1, ptr addrspace(2) %o, align 1
           br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_PhiShift0(self):
        # :see: PyArrShift, same as test_PhiChain0
        llvmIr = """\
        define void @PhiShift0(ptr addrspace(1) %i, ptr addrspace(2) %o)  {
        bb0:
          br label %bb1
        
        bb1:
          %phi = phi i16 [ 0, %bb0 ], [ %newPhiVal, %bb1 ]
          %phiB0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %phi, i5 0) #2
          %phiB1 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %phi, i5 8) #2
          %i_read = load volatile i8, ptr addrspace(1) %i, align 1
          store volatile i8 %phiB1, ptr addrspace(2) %o, align 1
          %newPhiVal = call i16 @hwtHls.bitConcat.i8.i8(i8 %i_read, i8 %phiB0) #2
          br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_PhiShiftWithShuffle(self):
        # :see: based shift of state regs in md5
        llvmIr = """\
        define void @PhiShiftWithShuffle(ptr addrspace(1) %din, ptr addrspace(2) %dout) {
        bb0:
          %din_read = load volatile i32, ptr addrspace(1) %din, align 4
          br label %bbHeader
        
        bbHeader:
          %shiftPhi = phi i128 [ 21528975894082904090066538856997790465, %bb0 ], [ %shiftPhi.1, %bbHeader ]
          
          %shiftPhi.32to64 = call i32 @hwtHls.bitRangeGet.i128.i8.i32.32(i128 %shiftPhi, i8 32) #2
          %shiftPhi.96to128 = call i32 @hwtHls.bitRangeGet.i128.i8.i32.96(i128 %shiftPhi, i8 96) #2
  
          %shiftPhi.add = add i32 %din_read, %shiftPhi.32to64
          %shiftPhi.32to96 = call i64 @hwtHls.bitRangeGet.i128.i8.i64.32(i128 %shiftPhi, i8 32) #2
          %shiftPhi.1 = call i128 @hwtHls.bitConcat.i32.i32.i64(i32 %shiftPhi.96to128, i32 %shiftPhi.add, i64 %shiftPhi.32to96) #2
          store volatile i128 %shiftPhi.1, ptr addrspace(2) %dout, align 4
          br label %bbHeader
        }
        """
        self._test_ll(llvmIr)

    def test_PhiWithConstValues(self):
        # :see: HlsPythonTupleAssign 8b 0 and 1 variables swapped and written out
        llvmIr = """\
        define void @PhiWithConstValues(ptr addrspace(1) %o0, ptr addrspace(2) %o1) {
          bb0:
            br label %bb1
          
          bb1:
            %shiftPhi = phi i16 [ 256, %bb0 ], [ %2, %bb1 ]
            %0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %shiftPhi, i5 0) #2
            %1 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %shiftPhi, i5 8) #2
            store volatile i8 %0, ptr addrspace(1) %o0, align 1
            store volatile i8 %1, ptr addrspace(2) %o1, align 1
            %2 = call i16 @hwtHls.bitConcat.i8.i8(i8 %1, i8 %0) #2
            br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_phiInitToUndef0a(self):
        llvmIr = """\
        define void @phiInitToUndef0a(ptr addrspace(1) %dout, ptr addrspace(3) %timerTick, ptr addrspace(4) %uart) {
            bb11:
              br label %bb14
            
            bb14:                                             ; preds = %bb11, %bb14
              %shiftPhi = phi i7 [ undef, %bb11 ], [ %data0, %bb14 ]
              %0 = call i6 @hwtHls.bitRangeGet.i7.i4.i6.1(i7 %shiftPhi, i4 1) #2
              %uart0 = load volatile i1, ptr addrspace(4) %uart, align 1
              %data0 = call i7 @hwtHls.bitConcat.i6.i1(i6 %0, i1 %uart0) #2
              store volatile i7 %data0, ptr addrspace(1) %dout, align 1
              br label %bb14
            }
        """
        self._test_ll(llvmIr)

    def test_phiInitToUndef0b(self):
        # :note: phiInitToUndef0a with order of phi operands reversed
        llvmIr = """\
        define void @phiInitToUndef0b(ptr addrspace(1) %dout, ptr addrspace(3) %timerTick, ptr addrspace(4) %uart) {
            bb11:
              br label %bb14
            
            bb14:                                             ; preds = %bb11, %bb14
              %shiftPhi = phi i7 [ %data0, %bb14 ], [ undef, %bb11 ] 
              %0 = call i6 @hwtHls.bitRangeGet.i7.i4.i6.1(i7 %shiftPhi, i4 1) #2
              %uart0 = load volatile i1, ptr addrspace(4) %uart, align 1
              %data0 = call i7 @hwtHls.bitConcat.i6.i1(i6 %0, i1 %uart0) #2
              store volatile i7 %data0, ptr addrspace(1) %dout, align 1
              br label %bb14
            }
        """
        self._test_ll(llvmIr)

    def test_phiInitToUndef1(self):
        # :note: same as phiInitToUndef0 with 2 nested loops
        llvmIr = """\
        define void @PhiInitToUndef1(ptr addrspace(1) %dout, ptr addrspace(3) %timerTick, ptr addrspace(4) %uart) {
            bb11:
              br label %bb14
            
            bb14:                                             ; preds = %bb11, %bb24
              %cntr0 = phi i4 [ %"37", %bb24 ], [ 7, %bb11 ]
              %shiftPhi = phi i7 [ %data0, %bb24 ], [ undef, %bb11 ]
              %0 = call i6 @hwtHls.bitRangeGet.i7.i4.i6.1(i7 %shiftPhi, i4 1) #2
              br label %bb16
            
            bb16:                                             ; preds = %bb17, %bb14
              %timerTick.0 = load volatile i1, ptr addrspace(3) %timerTick, align 1
              br i1 %timerTick.0, label %bb20, label %bb17
            
            bb17:                                             ; preds = %bb16
              br label %bb16
            
            bb20:                                             ; preds = %bb16, %bb21
              %timerTick.1 = load volatile i1, ptr addrspace(3) %timerTick, align 1
              br i1 %timerTick.1, label %bb24, label %bb21
            
            bb21:                                             ; preds = %bb20
              br label %bb20
            
            bb24:                                             ; preds = %bb20
              %uart0 = load volatile i1, ptr addrspace(4) %uart, align 1
              %"37" = add nsw i4 %cntr0, -1
              %"38" = icmp sgt i4 %cntr0, 0
              %data0 = call i7 @hwtHls.bitConcat.i6.i1(i6 %0, i1 %uart0) #2
              store volatile i7 %data0, ptr addrspace(1) %dout, align 1
              br i1 %"38", label %bb14, label %bb27
            
            bb27:                                             ; preds = %bb24
              ret void
        }
        """
        self._test_ll(llvmIr)

    def test_phiWithShiftIn(self):
        # :note: based on HlsPythonHwWhile4
        llvmIr = """\
        define void @test_phiWithShiftIn(ptr addrspace(1) %i, ptr addrspace(2) %o)  {
        bb0:
          br label %LCntr
        
        LCntr:                                            ; preds = %LFinalWrite, %LCntr, %bb0
          %cntr.03 = phi i4 [ 7, %LFinalWrite ], [ %1, %LCntr ], [ 7, %bb0 ]
          %data.0.shiftPhi = phi i7 [ %2, %LFinalWrite ], [ %2, %LCntr ], [ undef, %bb0 ]
          %0 = call i6 @hwtHls.bitRangeGet.i7.i4.i6.1(i7 %data.0.shiftPhi, i4 1) #2
          %i_read1 = load volatile i1, ptr addrspace(1) %i, align 1
          %1 = add nsw i4 %cntr.03, -1
          %.not = icmp eq i4 %cntr.03, 0
          %2 = call i7 @hwtHls.bitConcat.i6.i1(i6 %0, i1 %i_read1) #2
          br i1 %.not, label %LFinalWrite, label %LCntr
        
        LFinalWrite:                                      ; preds = %LCntr
          %3 = call i8 @hwtHls.bitConcat.i7.i1(i7 %data.0.shiftPhi, i1 %i_read1) #2
          store volatile i8 %3, ptr addrspace(2) %o, align 1
          br label %LCntr
        }
        """
        self._test_ll(llvmIr)

    def test_phiTrunc(self):
        # :note: based on fixpDivremRestoring
        llvmIr = """\
        define void @test_phiTrunc(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
        bb0:
          br label %bb1
        
        bb1:                                              ; preds = %bb4, %bb0
          %inpData_divisor.0 = phi i16 [ %13, %bb4 ], [ 0, %bb0 ]
          %0 = trunc i16 %inpData_divisor.0 to i1
          %1 = trunc i16 %inpData_divisor.0 to i1
          %invertQuotient4 = and i1 %1, %0
          %2 = sub nsw i16 0, 0
          %inpData_divisor.1 = select i1 %0, i16 %2, i16 0
          %3 = trunc nsw i16 %inpData_divisor.1 to i13
          %4 = and i13 %3, 4095
          br i1 false, label %bb2, label %bb4
        
        bb2:                                              ; preds = %bb2, %bb1
          %acc.046 = phi i16 [ 0, %bb1 ], [ %11, %bb2 ]
          %quotient.045 = phi i16 [ 0, %bb1 ], [ %10, %bb2 ]
          %5 = trunc nuw i16 %acc.046 to i13
          %6 = icmp ule i13 0, %5
          %7 = select i1 %6, i13 %4, i13 0
          %accNext2236 = sub i13 %5, %7
          %8 = trunc i13 %accNext2236 to i12
          %9 = call i13 @hwtHls.bitConcat.i1.i12(i1 false, i12 %8) #2
          %10 = zext i1 %6 to i16
          %11 = zext i13 %9 to i16
          br i1 false, label %bb3, label %bb2
        
        bb3:                                              ; preds = %bb2
          %quotient.3.le.le = select i1 %invertQuotient4, i16 %quotient.045, i16 0
          %12 = zext i16 %quotient.3.le.le to i24
          store volatile i24 %12, ptr addrspace(2) %data_out, align 4
          br label %bb4
        
        bb4:                                              ; preds = %bb3, %bb1
          %data_in_read1 = load volatile i25, ptr addrspace(1) %data_in, align 4
          %13 = trunc i25 %data_in_read1 to i16
          br label %bb1
        }
        """

        # from tests.stripInstructionsUnrelatedToCrash import llmIrStripInstrucionsUnrelatedToCrash
        # llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm), logAfterChange=True)
        # print(str(llvm.main))
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(BitwidthReductionPass_PHI_inLoopHeader_TC)
    # suite = unittest.TestSuite([BitwidthReductionPass_PHI_inLoopHeader_TC('test_phiWithShiftIn')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
