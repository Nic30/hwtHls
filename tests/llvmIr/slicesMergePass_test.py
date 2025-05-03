#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class SlicesMergePass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        # llvm.addLlvmCliArgOccurence("debug-only", 0, "", "newgvn")
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

    def test_phiSelect(self):
        ir = """\
        define void @ExampleCam.updateThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %write) {
        bb0:
          br label %bb.header
        
        bb.header:
          %k1_key.0 = phi i16 [ undef, %bb0 ], [ %k1_key.0, %bb.sw_c3 ], [ %k1_key.0, %bb.sw_c2 ], [ %5, %bb.sw_c1 ], [ %k1_key.0, %bb.header ]
          %k0_key.0 = phi i16 [ undef, %bb0 ], [ %k0_key.0, %bb.sw_c3 ], [ %k0_key.0, %bb.sw_c2 ], [ %k0_key.0, %bb.sw_c1 ], [ %5, %bb.header ]
          %k0_vld.018 = phi i1 [ false, %bb0 ], [ %k0_vld.018, %bb.sw_c3 ], [ %k0_vld.018, %bb.sw_c2 ], [ %k0_vld.018, %bb.sw_c1 ], [ %4, %bb.header ]
          %k1_vld.020 = phi i1 [ false, %bb0 ], [ %k1_vld.020, %bb.sw_c3 ], [ %k1_vld.020, %bb.sw_c2 ], [ %4, %bb.sw_c1 ], [ %k1_vld.020, %bb.header ]
          %0 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k0_key.0, i1 %k0_vld.018) #2
          store volatile i17 %0, ptr addrspace(1) %keyForMatchThread_0, align 4
          %1 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k1_key.0, i1 %k1_vld.020) #2
          store volatile i17 %1, ptr addrspace(2) %keyForMatchThread_1, align 4
          %write_read = load volatile i19, ptr addrspace(3) %write, align 4
          %4 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %write_read, i6 18) #2
          %5 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.2(i19 %write_read, i6 2) #2
          %6 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19 %write_read, i6 0) #2
          switch i2 %6, label %bb.header.unreachabledefault [
            i2 0, label %bb.header
            i2 1, label %bb.sw_c1
            i2 -2, label %bb.sw_c2
            i2 -1, label %bb.sw_c3
          ]
        
        bb.header.unreachabledefault:
          unreachable
        
        bb.sw_c1:
          br label %bb.header
        
        bb.sw_c2:
          br label %bb.header
        
        bb.sw_c3:
          br label %bb.header
        }
        """
        self._test_ll(ir)

    def test_nestedAnd(self):
        # read 3x i3 and then perform and of them each bit separately
        # in this test it is important how ands are ordered
        # its main purpose is to check that merged instructions are
        # built on correct place in recursive rewrite of concat
        ir = """\
        define void @nestedAnd(ptr addrspace(1) %i, ptr addrspace(2) %o) {
          %r0 = load volatile i3, ptr addrspace(1) %i, align 4
          %r1 = load volatile i3, ptr addrspace(1) %i, align 4
          %r2 = load volatile i3, ptr addrspace(1) %i, align 4
          %r0.0 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %r0, i3 0) #2
          %r0.1 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %r0, i3 1) #2
          %r0.2 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %r0, i3 2) #2
          %r1.0 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %r1, i3 0) #2
          %r1.1 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %r1, i3 1) #2
          %r1.2 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %r1, i3 2) #2
          %r2.0 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %r2, i3 0) #2
          %r2.1 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %r2, i3 1) #2
          %w0.0 = and i1 %r0.0, %r1.0 
          %w0 = and i1 %w0.0, %r2.0
          %w1.0 = and i1 %r0.1, %r1.1
          %w1 = and i1 %w1.0, %r2.1
          %r2.2 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %r2, i3 2) #2
          %w2.0 = and i1 %r0.2, %r1.2
          %w2 = and i1 %w2.0, %r2.2
          %w = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %w0, i1 %w1, i1 %w2) #2 ; :note: name "w" is not preserved because replacement is used by slices at that time
          store volatile i3 %w, i8 addrspace(2)* %o, align 1
          ret void
        }
        """
        self._test_ll(ir)

    def test_multilevelXorNestedInConcat(self):
        # xor should not be merged because w1 depends on w0
        ir = """\
        define void @multilevelXorNestedInConcat(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          %r0 = load volatile i1, ptr addrspace(1) %i, align 1
          %r1 = load volatile i1, ptr addrspace(1) %i, align 1
          %w0 = xor i1 %r0, true
          %w1 = xor i1 %w0, true
          %w = call i2 @hwtHls.bitConcat.i1.i1(i1 %w0, i1 %w1) #2
          store volatile i2 %w, ptr addrspace(2) %o, align 8
          ret void
        }
        """
        self._test_ll(ir)

    def test_multilevelXorNestedInConcat1(self):
        ir = """\
        define void @multilevelXorNestedInConcat1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          %r0 = load volatile i1, ptr addrspace(1) %i, align 1
          %r1 = load volatile i1, ptr addrspace(1) %i, align 1
          %r2 = load volatile i1, ptr addrspace(1) %i, align 1
          %r3 = load volatile i1, ptr addrspace(1) %i, align 1
          %r4 = load volatile i1, ptr addrspace(1) %i, align 1
          %r5 = load volatile i1, ptr addrspace(1) %i, align 1
          %w0 = xor i1 %r0, %r1
          %w0.1 = xor i1 %w0, %r5
          %w1 = xor i1 %r1, %r2
          %w5 = xor i1 %w1, %r3
          %w3 = call i2 @hwtHls.bitConcat.i1.i1(i1 %r0, i1 %r1) #2
          store volatile i2 %w3, ptr addrspace(2) %o, align 8
          %w4 = xor i1 %w0, %r4
          %w6 = call i2 @hwtHls.bitConcat.i1.i1(i1 %w4, i1 %w5) #2
          store volatile i1 %w0.1, ptr addrspace(2) %o, align 8
          store volatile i2 %w6, ptr addrspace(2) %o, align 8
          ret void
        }
        """
        self._test_ll(ir)

    def test_pktTrim(self):
        ir = """\
        define void @pktTrim(ptr addrspace(0) %lenIn, ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %bb1
        
        bb1:
          %len = load volatile i11, ptr addrspace(0) %lenIn, align 1
          %r0 = load volatile i1, ptr addrspace(1) %rx, align 1
          %r1 = load volatile i1, ptr addrspace(1) %rx, align 1
          %r2 = load volatile i1, ptr addrspace(1) %rx, align 1
          %r3 = load volatile i1, ptr addrspace(1) %rx, align 1
          %2 = xor i1 %r0, true
          %3 = and i1 %r1, %2
          %w0 = icmp eq i11 %len, -648
          %4 = icmp ne i11 %len, -648
          %7 = xor i1 %3, true
          %8 = or i1 %w0, %7
          %w1 = and i1 %4, %7
          %15 = xor i1 %r2, true
          %16 = and i1 %r1, %15
          %17 = xor i1 %16, true
          %18 = and i1 %7, %17
          %w2 = and i1 %4, %18
          %20 = xor i1 %r3, true
          %21 = and i1 %r1, %20
          %22 = xor i1 %21, true
          %23 = and i1 %18, %22
          %w3 = and i1 %4, %23
          %24 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %w1, i1 %w2, i1 %w3) #2
          store volatile i3 %24, ptr addrspace(2) %tx, align 8
          br label %bb1
        }
        """
        self._test_ll(ir)

    def test_constFold_Xor(self):
        ir = """\
        define void @test_constFold_Xor(i8 addrspace(1)* %i0, i8 addrspace(1)* %i1, i4 addrspace(2)* %o0, i4 addrspace(2)* %o1) {
            %i00 = load volatile i8, i8 addrspace(1)* %i0, align 1
            %i10 = load volatile i8, i8 addrspace(1)* %i1, align 1
            %"0" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i00, i64 0) #2
            %"1" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i00, i64 4) #2
            %"2" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i10, i64 0) #2
            %"3" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i10, i64 4) #2
            %"4" = xor i4 %"0", %"2"
            %"5" = xor i4 %"1", %"3"
            %"6" = xor i4 3,  0
            store volatile i4 %"4", i4 addrspace(2)* %o0, align 1
            store volatile i4 %"5", i4 addrspace(2)* %o1, align 1
            store volatile i4 %"6", i4 addrspace(2)* %o1, align 1
            ret void
        }
        """
        self._test_ll(ir)

    def test_constConcat(self):
        ir = """\
        define void @test_constConcat(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb0:
          %dataIn_read = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %0 = call i2 @hwtHls.bitRangeGet.i8.i4.i2.6(i8 0, i4 0) #2
          %1 = call i4 @hwtHls.bitConcat.i2.i2(i2 0, i2 %0) #2
          %.opConc = xor i4 %1, 0
          store volatile i16 0, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(ir)

    def test_constBitRangeGet(self):
        ir = """\
        define void @test_constBitRangeGet(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb0:
          %dataIn_read = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %0 = xor i5 0, 0
          %1 = call i1 @hwtHls.bitRangeGet.i5.i4.i1.4(i5 %0, i4 4) #2
          %2 = call i2 @hwtHls.bitConcat.i1.i1(i1 false, i1 false) #2 ; concat is important there, it trigers slice consystency checks
          store volatile i1 %1, ptr addrspace(2) %dataOut, align 2
          store volatile i2 %2, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(ir)

    def test_CRC_16_CDMA2000_8b_reduced0(self):
        ir = """\
        define void @test_CRC_16_CDMA2000_8b_reduced0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb0:
          %dataIn_read = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %0 = xor i1 false, false
          %1 = xor i1 false, %0
          %2 = xor i1 false, %1
          %3 = xor i1 false, false
          %4 = xor i1 false, %3
          %5 = xor i1 false, %4
          %6 = call i16 @hwtHls.bitConcat.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1(i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i1 %5, i1 %2, i1 false) #2
          store volatile i16 %6, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(ir)

    def test_CRC_16_CDMA2000_8b_reduced1(self):
        ir = """\
        define void @test_CRC_16_CDMA2000_8b_reduced1(ptr addrspace(1) %dataOut) {
        bb0:
          %"0" = xor i1 false, false
          %"1" = xor i1 false, %"0"
          %"2" = xor i1 false, false
          %"3" = xor i1 false, %"2"
          %"6" = xor i1 false, %"0"
          %"7" = xor i1 false, %"6"
          %"8" = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %"7", i1 %"3", i1 %"1") #2
          store volatile i3 %"8", ptr addrspace(1) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(ir)

    def test_CRC_16_CDMA2000_8b_reduced3(self):
        ir = """\
define void @test_CRC_16_CDMA2000_8b_reduced3(ptr addrspace(1) %dataOut) {
bb0:
  %"0" = xor i1 false, false
  %"2" = xor i1 false, false
  %"6" = xor i1 false, %"0"
  %"3" = xor i1 false, %"2"
  %"7" = xor i1 false, %"6"
  %"8" = call i2 @hwtHls.bitConcat.i1.i1(i1 %"7", i1 %"3") #2
  store volatile i2 %"8", ptr addrspace(1) %dataOut, align 2
  ret void
}
        """
        # llmIrStripInstrucionsUnrelatedToCrash(ir, lambda llvm: llvm._testSlicesMergePass())
        self._test_ll(ir)

    def test_CRC_16_CDMA2000_8b_reduced(self):
        ir = """\
define void @test_CRC_16_CDMA2000_8b_reduced2(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb0:
  %dataIn_read = load volatile i8, ptr addrspace(1) %dataIn, align 1
  %0 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.6(i8 %dataIn_read, i4 6) #2
  %1 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.7(i8 %dataIn_read, i4 7) #2
  %2 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.1(i8 %dataIn_read, i4 1) #2
  %3 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.5(i8 %dataIn_read, i4 5) #2
  %4 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.4(i8 %dataIn_read, i4 4) #2
  %5 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.3(i8 %dataIn_read, i4 3) #2
  %6 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.2(i8 %dataIn_read, i4 2) #2
  %7 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.0(i8 %dataIn_read, i4 0) #2
  %8 = xor i1 %7, %6
  %9 = xor i1 %5, %8
  %10 = xor i1 %4, %9
  %11 = xor i1 %3, %10
  %12 = xor i1 %7, %2
  %13 = xor i1 %3, %12
  %14 = xor i1 %1, %13
  %15 = xor i1 %6, %5
  %16 = xor i1 %3, %15
  %17 = xor i1 %0, %16
  %18 = xor i1 %2, %6
  %19 = xor i1 %4, %18
  %20 = xor i1 %3, %19
  %21 = xor i1 %1, %20
  %22 = xor i1 %5, %12
  %23 = xor i1 %4, %22
  %24 = xor i1 %0, %23
  %25 = xor i1 %1, %24
  %26 = xor i1 %4, %0
  %27 = xor i1 %1, %26
  %28 = xor i1 %5, %3
  %29 = xor i1 %0, %28
  %30 = xor i1 %1, %29
  %31 = xor i1 %6, %4
  %32 = xor i1 %3, %31
  %33 = xor i1 %0, %32
  %34 = xor i1 %2, %5
  %35 = xor i1 %4, %34
  %36 = xor i1 %3, %35
  %37 = xor i1 %1, %10
  %38 = xor i1 %4, %12
  %39 = xor i1 %3, %38
  %40 = xor i1 %0, %39
  %41 = xor i1 %6, %1
  %42 = xor i1 %2, %0
  %43 = xor i1 %1, %42
  %44 = xor i1 %7, %3
  %45 = xor i1 %0, %44
  %46 = xor i1 %1, %9
  %47 = xor i1 %3, %23
  %48 = xor i1 %0, %47
  %49 = call i16 @hwtHls.bitConcat.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1(i1 %48, i1 %46, i1 %45, i1 %43, i1 %41, i1 %40, i1 %37, i1 %36, i1 %33, i1 %30, i1 %27, i1 %25, i1 %21, i1 %17, i1 %14, i1 %11) #2
  store volatile i16 %49, ptr addrspace(2) %dataOut, align 2
  ret void;
}
        """

        # llmIrStripInstrucionUnrelatedToCrash(ir, lambda llvm: llvm._testSlicesMergePass())
        self._test_ll(ir)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle
    # m = SliceBreak3()
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SlicesMergePass_TC('test_pktTrim')])
    suite = testLoader.loadTestsFromTestCase(SlicesMergePass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
