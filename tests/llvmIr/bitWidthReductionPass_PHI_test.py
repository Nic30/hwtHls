#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.llvmIr.bitWidthReduction_test import BitwidthReductionPass_TC
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


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


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BitwidthReductionPass_PHI_TC('test_loopCondBitSet')])
    suite = testLoader.loadTestsFromTestCase(BitwidthReductionPass_PHI_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
