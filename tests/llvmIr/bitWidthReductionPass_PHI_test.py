#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.bitWidthReduction_test import BitwidthReductionPass_TC
# from tests.stripInstructionsUnrelatedToCrash import llmIrStripInstrucionsUnrelatedToCrash


class BitwidthReductionPass_PHI_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return BitwidthReductionPass_TC._runTestOpt(self, llvm)

    def test_rmInTheMiddle0(self):
        #  rxRaw = rx.read()
        #  if rxRaw.last:
        #     rxData = rxRaw.data[8:0]
        #  else:
        #     rxData = rxRaw.data[16:8]
        #  tx.write(rxData)

        llvmIr0 = """\
        define void @rmInTheMiddle0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
          BB0:
            br label %BB1
          BB1:
            %rxRaw = load volatile i19, ptr addrspace(1) %rx, align 4
            %rxData = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %rxRaw, i6 0) #2
            %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw, i6 18) #2
            %rxData0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %rxData, i5 0) #2
            br i1 %rxLast, label %BBv0, label %BBv1

          BBv0:
            %rxPhi_0 = call i10 @hwtHls.bitConcat.i8.i2(i8 %rxData0, i2 3) #2
            br label %BBend
          BBv1:
            %rxPhi_1 = call i10 @hwtHls.bitConcat.i8.i2(i8 %rxData0, i2 3) #2
            br label %BBend
          BBend:
            %rxPhi = phi i10 [ %rxPhi_0, %BBv0 ], [ %rxPhi_1, %BBv1 ]
            %rxFinalRaw = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rxPhi, i5 0) #2
            store volatile i8 %rxFinalRaw, ptr addrspace(2) %tx, align 4
            ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_rmInTheMiddle1(self):
        #  rxRaw = rx.read()
        #  if rxRaw.last:
        #     rxData = rxRaw.data[8:0]
        #  else:
        #     rxData = rxRaw.data[16:8]
        #  tx.write(rxData)

        llvmIr0 = """\
        define void @rmInTheMiddle1(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
          BB0:
            br label %BB1
          BB1:
            %rxRaw = load volatile i19, ptr addrspace(1) %rx, align 4
            %rxData = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %rxRaw, i6 0) #2
            %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw, i6 18) #2
            br i1 %rxLast, label %BBv0, label %BBv1

          BBv0:
            %rxData0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %rxData, i5 0) #2
            %rxPhi_0 = call i10 @hwtHls.bitConcat.i8.i2(i8 %rxData0, i2 3) #2
            br label %BBend
          BBv1:
            %rxData1 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.1(i16 %rxData, i5 1) #2
            %rxPhi_1 = call i10 @hwtHls.bitConcat.i8.i2(i8 %rxData1, i2 3) #2
            br label %BBend
          BBend:
            %rxPhi = phi i10 [ %rxPhi_0, %BBv0 ], [ %rxPhi_1, %BBv1 ]
            %rxFinalRaw = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rxPhi, i5 0) #2
            store volatile i8 %rxFinalRaw, ptr addrspace(2) %tx, align 4
            ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_rmInTheMiddle2(self):
        #  rxRaw = rx.read()
        #  if rxRaw.last:
        #     rxData = rxRaw.data[8:0]
        #  else:
        #     rxData = rxRaw.data[16:8]
        #  tx.write(rxData)

        llvmIr0 = """\
        define void @rmInTheMiddle2(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
          BB0:
            br label %BB1
          BB1:
            %rxRaw = load volatile i19, ptr addrspace(1) %rx, align 4
            %rxData = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %rxRaw, i6 0) #2
            %rxStrb = call i2 @hwtHls.bitRangeGet.i19.i6.i2.16(i19 %rxRaw, i6 16) #2
            %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw, i6 18) #2
            br i1 %rxLast, label %BBv0, label %BBv1

          BBv0:
            %rxData0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %rxData, i5 0) #2
            %rxPhi_0 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %rxData0, i1 1, i1 %rxLast) #2
            br label %BBend
          BBv1:
            %rxData1 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.1(i16 %rxData, i5 8) #2
            %rxPhi_1 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %rxData1, i1 1, i1 %rxLast) #2
            br label %BBend
          BBend:
            %rxPhi = phi i10 [ %rxPhi_0, %BBv0 ], [ %rxPhi_1, %BBv1 ]
            %rxFinalRaw = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rxPhi, i5 0) #2
            store volatile i8 %rxFinalRaw, ptr addrspace(2) %tx, align 4
            ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_rmInTheMiddle3(self):
        #  rxRaw = rx.read()
        #  if rxRaw.last:
        #     rxData = rxRaw.data[8:0]
        #  else:
        #     rxData = rxRaw.data[16:8]
        #  tx.write(rxData)

        llvmIr0 = """\
        define void @rmInTheMiddle3(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
          BB0:
            br label %BB1
          BB1:
            %rxRaw = load volatile i19, ptr addrspace(1) %rx, align 4
            %rxData = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %rxRaw, i6 0) #2
            %rxStrb = call i2 @hwtHls.bitRangeGet.i19.i6.i2.16(i19 %rxRaw, i6 16) #2
            %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw, i6 18) #2
            br i1 %rxLast, label %BBv0, label %BBv1

          BBv0:
            %rxData0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %rxData, i5 0) #2
            %rxStrb0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %rxStrb, i2 0) #2
            %rxPhi_0 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %rxData0, i1 %rxStrb0, i1 %rxLast) #2
            br label %BBend
          BBv1:
            %rxData1 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.1(i16 %rxData, i5 8) #2
            %rxStrb1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %rxStrb, i2 1) #2
            %rxPhi_1 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %rxData1, i1 %rxStrb1, i1 %rxLast) #2
            br label %BBend
          BBend:
            %rxPhi = phi i10 [ %rxPhi_0, %BBv0 ], [ %rxPhi_1, %BBv1 ]
            %rxFinalRaw = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rxPhi, i5 0) #2
            store volatile i8 %rxFinalRaw, ptr addrspace(2) %tx, align 4
            ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_rmInTheMiddle4(self):
        #  rxRaw = rx.read()
        #  if rxRaw.last:
        #     rxData = rxRaw.data[8:0]
        #  else:
        #     rxData = rxRaw.data[16:8]
        #  tx.write(rxData)

        llvmIr0 = """\
        define void @rmInTheMiddle4(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
          BB0:
            br label %BB1
          BB1:
            %rxRaw = load volatile i19, ptr addrspace(1) %rx, align 4
            %rxData = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %rxRaw, i6 0) #2
            %rxStrb = call i2 @hwtHls.bitRangeGet.i19.i6.i2.16(i19 %rxRaw, i6 16) #2
            %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw, i6 18) #2
            br i1 %rxLast, label %BBv0, label %BBv1

          BBv0:
            %rxData0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %rxData, i5 0) #2
            %rxStrb0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %rxStrb, i2 0) #2
            %rxPhi_0 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %rxData0, i1 %rxStrb0, i1 %rxLast) #2
            br label %BBend
          BBv1:
            %rxData1 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.1(i16 %rxData, i5 8) #2
            %rxStrb1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %rxStrb, i2 1) #2
            %rxPhi_1 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %rxData1, i1 %rxStrb1, i1 %rxLast) #2
            br label %BBend
          BBend:
            %rxPhi = phi i10 [ %rxPhi_0, %BBv0 ], [ %rxPhi_1, %BBv1 ]
            %rxFinalData0 = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rxPhi, i5 0) #2
            %rxFinalLast = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rxPhi, i5 9) #2
            %rxFinalData = call i16 @hwtHls.bitConcat.i8.i8(i8 %rxFinalData0, i8 0) #2
            %rxFinalRaw = call i19 @hwtHls.bitConcat.i16.i2.i1(i16 %rxFinalData, i2 1, i1 true) #2
            store volatile i19 %rxFinalRaw, ptr addrspace(2) %tx, align 4
            ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_constInConcat0(self):
        llvmIr = """\
        define void @constInConcat0(ptr addrspace(1) %rx, ptr addrspace(2) %txBody) {
            bb0:
              %rxRaw0 = load volatile i19, ptr addrspace(1) %rx, align 4
              %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw0, i6 18) #2
              %rxData0to8 = call i8 @hwtHls.bitRangeGet.i19.i6.i8.0(i19 %rxRaw0, i6 0) #2
              %rxData8to16 = call i8 @hwtHls.bitRangeGet.i19.i6.i8.8(i19 %rxRaw0, i6 8) #2
              %rxData = call i16 @hwtHls.bitConcat.i8.i8(i8 %rxData0to8, i8 %rxData8to16) #2
              %rxData0to8Zext16 = call i16 @hwtHls.bitConcat.i8.i8(i8 %rxData0to8, i8 0) #2
              br i1 %rxLast, label %bb1, label %bb2
            
            bb1:
              %rxRaw1 = call i19 @hwtHls.bitConcat.i16.i2.i1(i16 %rxData0to8Zext16, i2 1, i1 true) #2
              br label %bb3

            bb2:
              %rxRaw2 = call i19 @hwtHls.bitConcat.i16.i2.i1(i16 %rxData0to8Zext16, i2 -1, i1 true) #2
              br label %bb3

            bb3:
              %rxRawFinal = phi i19 [%rxRaw1, %bb1], [%rxRaw2, %bb2]
              store volatile i19 %rxRawFinal, ptr addrspace(2) %txBody, align 4
              ret void
        }
        """
        # 2. %rxData0to8 in rxData0to8Zext16 is not recognized to be the same and it is kept in phi
        self._test_ll(llvmIr)

    def test_phiConcAndNe(self):
        # based on IEEE754FpFromIntConventor res_sign phi
        llvmIr = """\
        define void @phiConcAndNe(ptr addrspace(1) %aIn, ptr addrspace(2) %bOut) {
        bb0:
          br label %bb.header

        bb.header:
          %a = load volatile i1, ptr addrspace(1) %aIn, align 4
          %b = load volatile i1, ptr addrspace(1) %aIn, align 4
          br i1 %a, label %bb.body, label %bb.latch

        bb.body:
          br label %bb.latch
        
        bb.latch:
          %res_sign = phi i1 [ false, %bb.header ], [ %b, %bb.body ]
          %res_sign.zext = call i8 @hwtHls.bitConcat.i1.i7(i1 %res_sign, i7 0) #2
          %res_sign.and = and i8 %res_sign.zext, 1
          %res_sign.ne = icmp ne i8 %res_sign.and, 0
          store volatile i1 %res_sign.ne, ptr addrspace(2) %bOut, align 4
          br label %bb.header
        }
        """
        self._test_ll(llvmIr)

    def test_phiRmLeftRight0(self):
        # based on Axi4SSParse2If SEGMENT_DATA_WIDTH=24 SEGMENT_CNT=1
        llvmIr = """\
        define void @phiRmLeftRight0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          br label %bb1
        
        bb1:   ; preds = %bb.latch, %bb1, %bb0
          %r0 = load volatile i28, ptr addrspace(1) %i, align 4
          %0 = call i16 @hwtHls.bitRangeGet.i28.i6.i16.0(i28 %r0, i6 0) #2
          %1 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.16(i28 %r0, i6 16) #2
          switch i16 %0, label %bb1 [
            i16 2, label %bb.off2
            i16 4, label %bb.off4
          ]
        
        bb.off2:  ; preds = %bb1
          %r.off2 = load volatile i28, ptr addrspace(1) %i, align 4
          br label %bb.latch
        
        bb.off4:  ; preds = %bb1
          %r.off4 = load volatile i28, ptr addrspace(1) %i, align 4
          br label %bb.latch
        
        bb.latch: ; preds = %bb.off2, %bb.off4
          %r.off.phi = phi i28 [ %r.off2, %bb.off2 ], [ %r.off4, %bb.off4 ]
          %6 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.26(i28 %r.off.phi, i6 26) #2
          %7 = icmp sgt i2 %6, -1 ; :note: combination of PHI and icmp is important in this test
          call void @llvm.assume(i1 %7) ; :note: this is test of that llvm.assume is recognized as value sink 
          store volatile i32 3, ptr addrspace(2) %o, align 4
          br label %bb1
        }
        """
        self._test_ll(llvmIr)


    def test_phiDoubleTrunc0(self):
        llvmIr = """\
        define void @test_phiDoubleTrunc0(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
        bb0:
          %r0 = load volatile i3, ptr addrspace(1) %data_in, align 4
          br label %bb3
        
        bb3:
          %it.0 = phi i3 [ %r0, %bb0 ], [ 0, %bb3 ]
          %it.1 = trunc i3 %it.0 to i2
          %it.2 = trunc i2 %it.1 to i1
          store volatile i1 %it.2, ptr addrspace(2) %data_out, align 2
          br label %bb3
        }
        """
        # llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm))
        # print(str(llvm.main))

        self._test_ll(llvmIr)

    def test_phiDoubleTrunc1(self):
        llvmIr = """\
        define void @test_phiDoubleTrunc1(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
        bb0:
          br label %bb3
        
        bb3:
          %it.0 = phi i3 [ poison, %bb0 ], [ 0, %bb3 ]
          %it.1 = trunc i3 %it.0 to i2
          %it.2 = trunc i2 %it.1 to i1
          store volatile i1 %it.2, ptr addrspace(2) %data_out, align 2
          br label %bb3
        }
        """
        # llvm = llmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm))
        # print(str(llvm.main))

        self._test_ll(llvmIr)

    def test_phiRmRight1(self):
        # :note: based on Axi4SSParse2If2B.mainThread 2seg 8b segment width 
        llvmIr = """\
        define void @test_phiRmRight1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          br label %bb3.streamSegSplit.1lane
        
        bb3.streamSegSplit.1lane:                         ; preds = %bb3.backedge.1lane, %bb0
          %0 = load volatile i20, ptr addrspace(1) %i, align 4
          %i_read1.r0.enable.0lane = call i1 @hwtHls.bitRangeGet.i20.i6.i1.16(i20 %0, i6 16) #2
          %1 = call i2 @hwtHls.bitRangeGet.i20.i6.i2.18(i20 %0, i6 18) #2
          %2 = call i8 @hwtHls.bitRangeGet.i20.i6.i8.8(i20 %0, i6 8) #2
          %3 = call i8 @hwtHls.bitRangeGet.i20.i6.i8.0(i20 %0, i6 0) #2
          %ld.s1 = call i10 @hwtHls.bitConcat.i8.i2(i8 %2, i2 %1) #2
          %4 = icmp eq i8 %3, 2
          %brmerge.not = and i1 %i_read1.r0.enable.0lane, %4
          %i_read1.r0.enable.0lane.not = xor i1 %i_read1.r0.enable.0lane, true
          br i1 %brmerge.not, label %bb5.sink.split.1lane, label %irr.guard
        
        bb3.backedge.0lane:                               ; preds = %irr.guard
          br i1 %i_read1.r0.enable.1lane, label %bb3.segmentEnCheckAfter.1lane, label %bb3.backedge.1lane
        
        bb3.backedge.1lane:                               ; preds = %bb3.backedge.0lane, %bb5.sink.split.1lane
          br label %bb3.streamSegSplit.1lane
        
        bb3.segmentEnCheckAfter.1lane:                    ; preds = %bb3.backedge.0lane
          br i1 %9, label %bb4.streamSegSplit.1lane, label %bb5.sink.split.1lane
        
        bb4.streamSegSplit.1lane:                         ; preds = %bb3.segmentEnCheckAfter.1lane
          %5 = load volatile i20, ptr addrspace(1) %i, align 4
          %6 = call i2 @hwtHls.bitRangeGet.i20.i6.i2.18(i20 %5, i6 18) #2
          %7 = call i8 @hwtHls.bitRangeGet.i20.i6.i8.8(i20 %5, i6 8) #2
          %8 = call i8 @hwtHls.bitRangeGet.i20.i6.i8.0(i20 %5, i6 0) #2
          %ld.s19 = call i10 @hwtHls.bitConcat.i8.i2(i8 %7, i2 %6) #2
          br label %bb5.sink.split.0lane
        
        bb5.sink.split.0lane:                             ; preds = %irr.guard, %bb4.streamSegSplit.1lane
          %i.1segment.0 = phi i10 [ %ld.s19, %bb4.streamSegSplit.1lane ], [ %ld.s1, %irr.guard ]
          %i_read_data.sink.0lane = phi i8 [ %8, %bb4.streamSegSplit.1lane ], [ %3, %irr.guard ]
          store volatile i8 %i_read_data.sink.0lane, ptr addrspace(2) %o, align 1
          br label %irr.guard
        
        bb5.sink.split.1lane:                             ; preds = %bb3.segmentEnCheckAfter.1lane, %bb3.streamSegSplit.1lane
          %i_read_data.sink.1lane = phi i8 [ %i_read1.r0.data.1lane, %bb3.segmentEnCheckAfter.1lane ], [ %2, %bb3.streamSegSplit.1lane ]
          store volatile i8 %i_read_data.sink.1lane, ptr addrspace(2) %o, align 1
          br label %bb3.backedge.1lane
        
        irr.guard:                                        ; preds = %bb3.streamSegSplit.1lane, %bb5.sink.split.0lane
          %i.1segment.1.moved = phi i10 [ %ld.s1, %bb3.streamSegSplit.1lane ], [ %i.1segment.0, %bb5.sink.split.0lane ]
          %Guard.bb3.backedge.0lane = phi i1 [ %i_read1.r0.enable.0lane.not, %bb3.streamSegSplit.1lane ], [ true, %bb5.sink.split.0lane ]
          %i_read1.r0.enable.1lane = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %i.1segment.1.moved, i5 8) #2
          %i_read1.r0.data.1lane = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %i.1segment.1.moved, i5 0) #2
          %9 = icmp eq i8 %i_read1.r0.data.1lane, 2
          br i1 %Guard.bb3.backedge.0lane, label %bb3.backedge.0lane, label %bb5.sink.split.0lane
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(BitwidthReductionPass_PHI_TC)
    # suite = unittest.TestSuite([BitwidthReductionPass_PHI_TC('test_phiRmRight1')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
