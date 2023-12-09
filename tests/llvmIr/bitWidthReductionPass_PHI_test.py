#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.llvmIr.bitWidthReduction_test import BitwidthReductionPass_TC
from tests.baseSsaTest import BaseSsaTC


class BitwidthReductionPass_PHI_TC(BaseSsaTC):
    __FILE__ = __file__

    def _test_ll(self, irStr:str):
        BitwidthReductionPass_TC._test_ll(self, irStr)

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


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BitwidthReductionPass_PHI_TC('test_rmInTheMiddle4')])
    suite = testLoader.loadTestsFromTestCase(BitwidthReductionPass_PHI_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
