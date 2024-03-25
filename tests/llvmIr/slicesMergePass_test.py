#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class SlicesMergePass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._testSlicesMergePass()

    def test_notingToReduce(self):
        llvmIr0 = """
        define void @notingToReduce() {
          ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_mergeConst(self):
        ir = """\
        define void @mergeConst(i8 addrspace(2)* %o) {
          %1 = call i8 @hwtHls.bitConcat.i4.i4(i4 1, i4 2) #2
          store volatile i8 %1, i8 addrspace(2)* %o, align 1
          ret void
        }
        """
        self._test_ll(ir)

    def test_mergeBecauseOfConcat(self):
        ir = """\
        define void @mergeBecauseOfConcat(i8 addrspace(1)* %i, i8 addrspace(2)* %o) {
          BB0:
            %i0 = load volatile i8, i8 addrspace(1)* %i, align 1
            %0 = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i0, i64 0) #2
            %1 = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i0, i64 4) #2
            br label %BB1

          BB1:
            %2 = call i8 @hwtHls.bitConcat.i4.i4(i4 %0, i4 %1) #2
            store volatile i8 %2, i8 addrspace(2)* %o, align 1
            br label %BB1
        }
        """
        self._test_ll(ir)

    def test_phiShift(self):
        ir = """\
        define void @phiShift(i4 addrspace(1)* %i, i4 addrspace(2)* %o) {
          BB0:
            br label %BB1

          BB1:
            %i0 = load volatile i4, i4 addrspace(1)* %i, align 1
            %0 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i0, i64 0) #2
            %1 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.1(i4 %i0, i64 1) #2
            %2 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.2(i4 %i0, i64 2) #2
            %3 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.3(i4 %i0, i64 3) #2
            br label %BB2
          BB2: ; i0 >>= 1
            %4 = phi i1 [ %0, %BB1 ], [ %5, %BB2 ]
            %5 = phi i1 [ %1, %BB1 ], [ %6, %BB2 ]
            %6 = phi i1 [ %2, %BB1 ], [ %7, %BB2 ]
            %7 = phi i1 [ %3, %BB1 ], [ 0, %BB2 ]
            store volatile i4 11, i4 addrspace(2)* %o, align 1
            br i1 %4, label %BB2, label %BB1 ; while (i0 & 1)
        }
        """
        self._test_ll(ir)

    def test_parallelAnd(self):
        ir = """\
        define void @parallelAnd(i8 addrspace(1)* %i0, i8 addrspace(1)* %i1, i4 addrspace(2)* %o0, i4 addrspace(2)* %o1) {
            %i00 = load volatile i8, i8 addrspace(1)* %i0, align 1
            %i10 = load volatile i8, i8 addrspace(1)* %i1, align 1
            %"0" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i00, i64 0) #2
            %"1" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i00, i64 4) #2
            %"2" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i10, i64 0) #2
            %"3" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i10, i64 4) #2
            %"4" = and i4 %"0", %"2"
            %"5" = and i4 %"1", %"3"
            store volatile i4 %"4", i4 addrspace(2)* %o0, align 1
            store volatile i4 %"5", i4 addrspace(2)* %o1, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_parallelSelect(self):
        ir = """\
        define void @parallelSelect(i8 addrspace(1)* %i0, i8 addrspace(1)* %i1, i4 addrspace(2)* %o0, i4 addrspace(2)* %o1) {
            %i00 = load volatile i8, i8 addrspace(1)* %i0, align 1
            %i10 = load volatile i8, i8 addrspace(1)* %i1, align 1
            %"c" = call i1 @hwtHls.bitRangeGet.i8.i64.i1.0(i8 %i00, i64 0) #2
            %"0" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i00, i64 0) #2
            %"1" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i00, i64 4) #2
            %"2" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i10, i64 0) #2
            %"3" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i10, i64 4) #2
            %"4" = select i1 %"c", i4 %"0", i4 %"2"
            %"5" = select i1 %"c", i4 %"1", i4 %"3"
            store volatile i4 %"4", i4 addrspace(2)* %o0, align 1
            store volatile i4 %"5", i4 addrspace(2)* %o1, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_parallelSelect2(self):
        # parallel selects where last one has constant falseVal operand
        ir = """\
        define void @parallelSelect2(i4 addrspace(1)* %i0, i4 addrspace(1)* %i1,
                                     i1 addrspace(2)* %o0, i1 addrspace(2)* %o1,
                                     i1 addrspace(2)* %o2, i1 addrspace(2)* %o3) {
            %i00 = load volatile i4, i4 addrspace(1)* %i0, align 1
            %i10 = load volatile i4, i4 addrspace(1)* %i1, align 1
            %"c" = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #2
            %1 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #2
            %2 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.1(i4 %i00, i64 1) #2
            %3 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.2(i4 %i00, i64 2) #2
            %4 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.3(i4 %i00, i64 3) #2
           
            %5 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i10, i64 0) #2
            %6 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.1(i4 %i10, i64 1) #2
            %7 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.2(i4 %i10, i64 2) #2
            ;%8 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.3(i4 %i10, i64 3) #2
           
            %sel0 = select i1 %c, i1 %1, i1 %5
            %sel1 = select i1 %c, i1 %2, i1 %6
            %sel2 = select i1 %c, i1 %3, i1 %7
            %sel3 = select i1 %c, i1 %4, i1 false
            store volatile i1 %sel0, i1 addrspace(2)* %o0, align 1
            store volatile i1 %sel1, i1 addrspace(2)* %o1, align 1
            store volatile i1 %sel2, i1 addrspace(2)* %o2, align 1
            store volatile i1 %sel3, i1 addrspace(2)* %o3, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_parallelSelect3(self):
        # select where falseVal operand is constant
        ir = """\
        define void @parallelSelect3(i4 addrspace(1)* %i0,
                                     i1 addrspace(2)* %o0, i1 addrspace(2)* %o1,
                                     i1 addrspace(2)* %o2, i1 addrspace(2)* %o3) {
            %i00 = load volatile i4, i4 addrspace(1)* %i0, align 1
            %"c" = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #2
            %1 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #2
            %2 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.1(i4 %i00, i64 1) #2
            %3 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.2(i4 %i00, i64 2) #2
            %4 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.3(i4 %i00, i64 3) #2
           
            %sel0 = select i1 %c, i1 %1, i1 false
            %sel1 = select i1 %c, i1 %2, i1 true
            %sel2 = select i1 %c, i1 %3, i1 false
            %sel3 = select i1 %c, i1 %4, i1 false
            store volatile i1 %sel0, i1 addrspace(2)* %o0, align 1
            store volatile i1 %sel1, i1 addrspace(2)* %o1, align 1
            store volatile i1 %sel2, i1 addrspace(2)* %o2, align 1
            store volatile i1 %sel3, i1 addrspace(2)* %o3, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_parallelSelect4(self):
        # select are interleaved with sinkable xor
        # :note: xor is immediately folded by llvm foldOperationIntoSelectOperand
        #  updating select operands
        ir = """\
        define void @parallelSelect4(i4 addrspace(1)* %i0,
                                     i1 addrspace(2)* %o0, i1 addrspace(2)* %o1,
                                     i1 addrspace(2)* %o2, i1 addrspace(2)* %o3) {
            %i00 = load volatile i4, i4 addrspace(1)* %i0, align 1
            %"c" = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #2
            %1 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #2
            %2 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.1(i4 %i00, i64 1) #2
            %3 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.2(i4 %i00, i64 2) #2
            %4 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.3(i4 %i00, i64 3) #2
           
            %sel0 = select i1 %c, i1 %1, i1 false
            %xor0 = xor i1 %sel0, true
            %sel1 = select i1 %c, i1 %2, i1 true
            %xor1 = xor i1 %sel1, true
            %sel2 = select i1 %c, i1 %3, i1 false
            %xor2 = xor i1 %sel2, true
            %sel3 = select i1 %c, i1 %4, i1 false
            %xor3 = xor i1 %sel3, true

            store volatile i1 %xor0, i1 addrspace(2)* %o0, align 1
            store volatile i1 %xor1, i1 addrspace(2)* %o1, align 1
            store volatile i1 %xor2, i1 addrspace(2)* %o2, align 1
            store volatile i1 %xor3, i1 addrspace(2)* %o3, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_parallelSelect5(self):
        ir = """\
        define void @parallelSelect5(i4 addrspace(1)* %i0,
                                     i1 addrspace(2)* %o0, i1 addrspace(2)* %o1,
                                     i1 addrspace(2)* %o2, i1 addrspace(2)* %o3) {
            %i00 = load volatile i4, i4 addrspace(1)* %i0, align 1
            %"c" = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #2

            %sel0 = select i1 %c, i1 false, i1 false
            %sel1 = select i1 %c, i1 false, i1 true
            %sel2 = select i1 %c, i1 true, i1 false
            %sel3 = select i1 %c, i1 true, i1 false

            store volatile i1 %sel0, i1 addrspace(2)* %o0, align 1
            store volatile i1 %sel1, i1 addrspace(2)* %o1, align 1
            store volatile i1 %sel2, i1 addrspace(2)* %o2, align 1
            store volatile i1 %sel3, i1 addrspace(2)* %o3, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_parallelMultipletimes(self):
        ir = """\
        define void @test_parallelMultipletimes(i2 addrspace(1)* %i0, i2 addrspace(1)* %i1,
                                     i1 addrspace(2)* %o0, i1 addrspace(2)* %o1) {
            %i00 = load volatile i2, i2 addrspace(1)* %i0, align 1
            %i0b0 = call i1 @hwtHls.bitRangeGet.i2.i64.i1.0(i2 %i00, i64 0) #2
            %i0b1 = call i1 @hwtHls.bitRangeGet.i2.i64.i1.1(i2 %i00, i64 1) #2

            %i10 = load volatile i2, i2 addrspace(1)* %i1, align 1
            %i1b0 = call i1 @hwtHls.bitRangeGet.i2.i64.i1.0(i2 %i10, i64 0) #2
            %i1b1 = call i1 @hwtHls.bitRangeGet.i2.i64.i1.1(i2 %i10, i64 1) #2
           
            %xor0 = xor i1 %i0b0, %i1b0
            %xor1 = xor i1 %i0b1, %i1b1
            
            
            %and0 = and i1 %i0b0, %i1b0
            %and1 = and i1 %i0b1, %i1b1
            %and2 = and i1 %and0, %and1
            
            %xor2 = xor i1 %xor0, %xor1
            
            store volatile i1 %xor2, i1 addrspace(2)* %o0, align 1
            store volatile i1 %and2, i1 addrspace(2)* %o1, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_parallelMultipletimes2(self):
        # parallelMultipletimes with partial results also stored
        ir = """\
        define void @test_parallelMultipletimes2(i2 addrspace(1)* %i0, i2 addrspace(1)* %i1,
                                     i1 addrspace(2)* %o0, i1 addrspace(2)* %o1, i1 addrspace(2)* %o2) {
            %i00 = load volatile i2, i2 addrspace(1)* %i0, align 1
            %i0b0 = call i1 @hwtHls.bitRangeGet.i2.i64.i1.0(i2 %i00, i64 0) #2
            %i0b1 = call i1 @hwtHls.bitRangeGet.i2.i64.i1.1(i2 %i00, i64 1) #2

            %i10 = load volatile i2, i2 addrspace(1)* %i1, align 1
            %i1b0 = call i1 @hwtHls.bitRangeGet.i2.i64.i1.0(i2 %i10, i64 0) #2
            %i1b1 = call i1 @hwtHls.bitRangeGet.i2.i64.i1.1(i2 %i10, i64 1) #2
           
            %xor0 = xor i1 %i0b0, %i1b0
            %xor1 = xor i1 %i0b1, %i1b1
            
            %and0 = and i1 %i0b0, %i1b0
            %and1 = and i1 %i0b1, %i1b1
            %and2 = and i1 %and0, %and1
            
            %xor2 = xor i1 %xor0, %xor1
            
            store volatile i1 %xor2, i1 addrspace(2)* %o0, align 1
            store volatile i1 %and2, i1 addrspace(2)* %o1, align 1
            store volatile i1 %xor0, i1 addrspace(2)* %o2, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_crc32_3b(self):
        ir = """\
        define void @test_crc32_3b(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
          %"dataIn0(dataIn_read)" = load volatile i3, ptr addrspace(1) %dataIn, align 1
          %"0" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %"dataIn0(dataIn_read)", i3 0) #2
          %"1" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %"dataIn0(dataIn_read)", i3 1) #2
          %"2" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %"dataIn0(dataIn_read)", i3 2) #2
          %"8" = xor i1 %"2", %"1"
          %"9" = xor i1 %"8", true
          %"15" = xor i1 %"2", true
          %"17" = xor i1 %"1", %"15"
          %"19" = xor i1 %"0", %"17"
          %"20" = xor i1 %"19", true
          %"26" = xor i1 %"1", true
          %"29" = xor i1 %"0", %"1"
          %"38" = xor i1 %"0", %"2"
          %"110" = xor i1 %"0", %"8"
          %"111" = xor i1 %"110", true
          %"126" = xor i1 %"0", true
          %"3" = call i32 @hwtHls.bitConcat.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i3.i1.i1.i1.i1.i1.i1.i1.i3(i1 %"2", i1 %"9", i1 %"20", i1 %"29", i1 %"38", i1 %"8", i1 %"29", i1 %"38", i1 %"8", i1 %"29", i1 %"38", i1 %"8", i1 %"111", i1 %"29", i1 %"126", i1 false, i1 %"15", i1 %"26", i1 %"126", i3 0, i1 %"15", i1 %"8", i1 %"29", i1 %"126", i1 %"15", i1 %"26", i1 %"126", i3 0) #2
          store volatile i32 %"3", ptr addrspace(2) %dataOut, align 4
          ret void
        }
        """
        self._test_ll(ir)

    def test_crc32_3b_reduced(self):
        ir = """\
        define void @test_crc32_3b_reduced(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
          %"dataIn0(dataIn_read)" = load volatile i3, ptr addrspace(1) %dataIn, align 1
          %"0" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %"dataIn0(dataIn_read)", i3 0) #2
          %"1" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %"dataIn0(dataIn_read)", i3 1) #2
          %"2" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %"dataIn0(dataIn_read)", i3 2) #2
          %"3" = xor i1 %"2", %"1"
          %"4" = and i1 %"0", %"3"
          %"5" = xor i1 %"4", true
          %"6" = call i2 @hwtHls.bitConcat.i1.i1(i1 %"3", i1 %"5") #2
          store volatile i2 %"6", ptr addrspace(2) %dataOut, align 4
          ret void
        }
        """
        self._test_ll(ir)

if __name__ == "__main__":
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # u = SliceBreak3()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SlicesMergePass_TC('test_crc32_3b_reduced')])
    suite = testLoader.loadTestsFromTestCase(SlicesMergePass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
