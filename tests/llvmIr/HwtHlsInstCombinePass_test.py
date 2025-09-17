#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function, FunctionPassManager, HwtHlsInstCombinePassOptions, \
    HwtHlsInstCombinePass, EarlyCSEPass, BitcountMergePass
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class HwtHlsInstCombinePass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, runBitcountMergePass=False, runStreamReadEoFThreading=False) -> Function:

        def _addHwtHlsInstCombinePass(FPM:FunctionPassManager):
            opts = HwtHlsInstCombinePassOptions()
            opts.extractBitcounts = runBitcountMergePass
            opts.streamReadEoFThreading = runStreamReadEoFThreading
            FPM.addPass(HwtHlsInstCombinePass(opts))
            if runBitcountMergePass:
                FPM.addPass(EarlyCSEPass());
                FPM.addPass(BitcountMergePass());
                FPM.addPass(HwtHlsInstCombinePass());
                FPM.addPass(EarlyCSEPass());

        return llvm._runCustomFunctionPass(_addHwtHlsInstCombinePass)

    def test_tryReduceConcatOnConcat(self):
        llvmIr = """\
        define void @test_tryReduceConcatOnConcat(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %r1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %c0 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %r0) #2
          %c1 = call i3 @hwtHls.bitConcat.i2.i1(i2 %c0, i1 %r1) #2
          store volatile i3 %c1, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceBitRangeGetOnConcat0(self):
        llvmIr = """\
        define void @test_tryReduceBitRangeGetOnConcat0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %r1 = load volatile i2, ptr addrspace(1) %dataIn, align 1
          %v2 = call i10 @hwtHls.bitConcat.i8.i2(i8 %r0, i2 %r1) #2
          %v3 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %v2, i5 9) #2
          store volatile i1 %v3, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_andOnConcatCostPropagation(self):
        # :note: this should not change as the optimization of and on constant is implemented in BitwidthReducePass
        llvmIr = """\
        define void @test_andOnConcatCostPropagation(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %r1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %c0 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %r0) #2
          %c1 = call i2 @hwtHls.bitConcat.i1.i1(i1 %r1, i1 true) #2
          %and0 = and i2 %c0, %c1        
          store volatile i2 %and0, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceCmpInst_hoistConstICmpOnConstArithAndSel_addNe(self):
        llvmIr = """\
        define void @test_tryReduceCmpInst_hoistConstICmpOnConstArithAndSel_addNe(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %r0_p1 = add i8 %r0, 1
          %res = icmp ne i8 %r0_p1, 10
          store volatile i1 %res, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceCmpInst_hoistConstICmpOnConstArithAndSel_icmpOptionalAdd(self):
        llvmIr = """\
        define void @test_tryReduceCmpInst_hoistConstICmpOnConstArithAndSel_icmpOptionalAdd(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
        bb.0:
          %r0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %c = load volatile i1, ptr addrspace(2) %condIn, align 1
          %r0_p1 = add i8 %r0, 1
          %r1 = select i1 %c, i8 %r0, i8 %r0_p1
          %res = icmp ne i8 %r1, 1
          store volatile i1 %res, ptr addrspace(3) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_andOfNe_usingSelect(self):
        llvmIr = """\
        define void @test_andOfNe_usingSelect(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
        bb.0:
          %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
          %c0.n = icmp ne i9 %v0, 8
          %c1 = icmp eq i9 %v0, 7
          %c0 = xor i1 %c0.n, true
          %c2 = icmp eq i9 %v0, 6
          %res = select i1 %c0, i1 %c1, i1 %c2
          store volatile i1 %res, ptr addrspace(3) %dataOut, align 2
          ret void
        }
        """

        self._test_ll(llvmIr)

    def test_andOfNe_usingSelect_nonNegatedCmp0(self):
        # :see: :meth:`~.test_andOfNe_usingSelect`
        llvmIr = """\
        define void @test_andOfNe_usingSelect_nonNegatedCmp0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
        bb.0:
          %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
          %cmp0 = icmp eq i9 %v0, 128
          %cmp1 = icmp eq i9 %v0, 127
          %cmp2 = icmp eq i9 %v0, 126
          %res = select i1 %cmp0, i1 %cmp1, i1 %cmp2
          store volatile i1 %res, ptr addrspace(3) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_andOfNe_usingSelect_nonNegatedCmp1(self):
        # :see: :meth:`~.test_andOfNe_usingSelect`
        # -> ; tryReduceSelectInst_unNegate
        # %res = select i1 %cmp0.n, i1 %cmp2.n, i1 %cmp1.n
        # -> ; _tryReduceSelectInst_toAndOr_SelectOfCompares
        # %0 = xor i1 %cmp0.n, true
        # %res = or i1 %0, %cmp2.n
        # ->
        # %cmp2.n = icmp ne i9 %v0, 124
        llvmIr = """\
        define void @test_andOfNe_usingSelect_nonNegatedCmp1(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
        bb.0:
          %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
          %cmp0.n = icmp ne i9 %v0, 128
          %cmp0 = xor i1 %cmp0.n, true
          %cmp1.n = icmp ne i9 %v0, 125
          %cmp2.n = icmp ne i9 %v0, 124
          %res = select i1 %cmp0, i1 %cmp1.n, i1 %cmp2.n
          store volatile i1 %res, ptr addrspace(3) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_andOfNe_usingSelect_0(self):
        # :see: :meth:`~.test_andOfNe_usingSelect`
        llvmIr = """\
        define void @test_andOfNe_usingSelect_0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
        bb.0:   
          %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
          
          %cmp.eq124 = icmp eq i9 %v0, 124
          %cmp.eq125 = icmp eq i9 %v0, 125
          %cmp.eq124_or_125 = or i1 %cmp.eq125, %cmp.eq124
          
          %cmp.ne127 = icmp ne i9 %v0, 127
          %cmp.ne128 = icmp ne i9 %v0, 128
          %cmp.ne127_and_128 = and i1 %cmp.ne128, %cmp.ne127
          %cmp.eq127_or_128 = xor i1 %cmp.ne127_and_128, true
          
          %cmp.ne122 = icmp ne i9 %v0, 122
          %cmp.ne123 = icmp ne i9 %v0, 123
          %cmp.ne122_and_123 = and i1 %cmp.ne123, %cmp.ne122
          %cmp.eq122_or_123 = xor i1 %cmp.ne122_and_123, true
          
          %res = select i1 %cmp.eq122_or_123, i1 %cmp.eq127_or_128, i1 %cmp.eq124_or_125 ; cmp.eq122_or_123 & cmp.eq127_or_128 == 0
          store volatile i1 %res, ptr addrspace(3) %dataOut, align 1
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceSelectInst_toAndOr0(self):
        llvmIr = """\
        define void @test_tryReduceSelectInst_toAndOr0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0: 
          %v0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %c0 = icmp ne i8 %v0, 8
          %c1 = icmp ne i8 %v0, 7
          %c2 = select i1 %c0, i1 %c0, i1 %c1 ; :note: reduces to true
          store volatile i1 %c2, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceSelectInst_toAndOr1(self):
        llvmIr = """\
        define void @test_tryReduceSelectInst_toAndOr1(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0: 
          %v0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %v1 = load volatile i3, ptr addrspace(1) %dataIn, align 1
          %v0.bit0 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.0(i8 %v0, i4 0) #2
          %c = icmp eq i3 %v1, -1
          %0 = call i8 @hwtHls.bitConcat.i7.i1(i7 0, i1 %v0.bit0) #2
          %res = select i1 %c, i8 %0, i8 %v0
          store volatile i8 %res, ptr addrspace(2) %dataOut, align 1
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceSelectInst_toAndOr2(self):
        # :note: test_tryReduceSelectInst_toAndOr1 with negated condition of select
        llvmIr = """\
        define void @test_tryReduceSelectInst_toAndOr2(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0: 
          %v0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
          %v1 = load volatile i3, ptr addrspace(1) %dataIn, align 1
          %v0.bit0 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.0(i8 %v0, i4 0) #2
          %c = icmp eq i3 %v1, -1
          %0 = call i8 @hwtHls.bitConcat.i7.i1(i7 0, i1 %v0.bit0) #2
          %1 = xor i1 %c, true
          %res = select i1 %1, i8 %v0, i8 %0
          store volatile i8 %res, ptr addrspace(2) %dataOut, align 1
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceSelectInst_toAndOr3(self):
        llvmIr = """\
        define void @test_tryReduceSelectInst_toAndOr3(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0: 
          %v0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %v1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %s0 = select i1 %v0, i1 %v1, i1 true
          %s1 = select i1 %v0, i1 %v1, i1 false
          store volatile i1 %s0, ptr addrspace(2) %dataOut, align 1
          store volatile i1 %s1, ptr addrspace(2) %dataOut, align 1
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceSelectInst_toAndOr4(self):
        llvmIr = """\
        define void @test_tryReduceSelectInst_toAndOr4(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0: 
          %v0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %v1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %vt = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %v0) #2
          %vf = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 true) #2 ; this is converted to -1 as a first step
          %res = select i1 %v1, i2 %vt, i2 %vf
          store volatile i2 %res, ptr addrspace(2) %dataOut, align 1
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceSelectInst_toAndOr5(self):
        llvmIr = """\
        define void @test_tryReduceSelectInst_toAndOr5(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        bb0:
          %i_read2 = load volatile i16, ptr addrspace(1) %i, align 2
          %0 = icmp eq i16 %i_read2, 10
          %.mux = select i1 %0, i16 20, i16 26
          store volatile i16 %.mux, ptr addrspace(2) %o, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReducePopcnt_toCTLZ(self):
        llvmIr = """\
        define void @test_tryReducePopcnt_toCTLZ(ptr addrspace(1) %condIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %c0 = load volatile i1, ptr addrspace(1) %condIn, align 1
          %c1.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
          %c2.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
          %c3.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
          %c1 = and i1 %c0, %c1.0
          %c2 = and i1 %c1, %c2.0
          %c3 = and i1 %c2, %c3.0
          %c = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 %c0, i1 %c1, i1 %c2, i1 %c3) #2
          %c.n = xor i4 %c, -1
          %res = call i4 @llvm.ctpop.i4(i4 %c.n)
          store volatile i4 %res, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReducePopcnt_toCTLO(self):
        llvmIr = """\
        define void @test_tryReducePopcnt_toCTLO(ptr addrspace(1) %condIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %c0 = load volatile i1, ptr addrspace(1) %condIn, align 1
          %c1.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
          %c2.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
          %c3.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
          %c1 = and i1 %c0, %c1.0
          %c2 = and i1 %c1, %c2.0
          %c3 = and i1 %c2, %c3.0
          %c = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 %c0, i1 %c1, i1 %c2, i1 %c3) #2
          %res = call i4 @llvm.ctpop.i4(i4 %c)
          store volatile i4 %res, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReducePopcnt_constBits(self):
        llvmIr = """\
        define void @test_tryReducePopcnt_constBits(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %v0 = load volatile i2, ptr addrspace(1) %dataIn, align 1
          %c0 = call i5 @hwtHls.bitConcat.i2.i3(i2 %v0, i3 -1) #2
          %res = call i5 @llvm.ctpop.i5(i5 %c0)
          store volatile i5 %res, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_tryReduceZExt_onZExt(self):
        llvmIr = """\
        define void @test_tryReduceZExt_onZExt(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %v0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
          %v0.0 = zext i1 %v0 to i4
          %v0.1 = zext i4 %v0.0 to i9
          store volatile i9 %v0.1, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    # def test_tryReduceAddSub_toSelect(self):
    #    llvmIr = """\
    #    define void @test_tryReduceAddSub_toSelect(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
    #    bb.0:
    #      %v = load volatile i9, ptr addrspace(1) %dataIn, align 1
    #      %v0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
    #      %v0.0 = zext i1 %v0 to i9
    #      %v1.0 = add i9 %v, %v0.0
    #      %v1.1 = add i9 %v0.0, %v
    #      %v2.0 = sub i9 %v, %v0.0
    #      %v2.1 = sub i9 %v0.0, %v
    #      store volatile i9 %v1.0, ptr addrspace(2) %dataOut, align 2
    #      store volatile i9 %v1.1, ptr addrspace(2) %dataOut, align 2
    #      store volatile i9 %v2.0, ptr addrspace(2) %dataOut, align 2
    #      store volatile i9 %v2.1, ptr addrspace(2) %dataOut, align 2
    #      ret void
    #    }
    #    """
    #    self._test_ll(llvmIr)

    # :note: deprecated because hoisting compares before select causes code explosion
    # def test_tryReduceConstCmpOnOptionalAddSub0(self):
    #    # eq, ne are comparing for a single point only and the rhs of "add" is a difference between rhs values of ICmps
    #    # this means that they are actually checking for a single point, but the check may be negated
    #    llvmIr = """\
    #    define void @test_tryReduceCmpOnOptionalAddSub0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
    #    bb.0:
    #      %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
    #      %c0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
    #      %v1 = add i9 %v0, 1
    #      %v2 = select i1 %c0, i9 %v1, i9 %v0
    #      %res0 = icmp ne i9 %v2, 128
    #      %res1 = icmp eq i9 %v2, 127
    #      store volatile i1 %res0, ptr addrspace(2) %dataOut, align 2
    #      store volatile i1 %res1, ptr addrspace(2) %dataOut, align 2
    #      ret void
    #    }
    #    """
    #    #  %v1 = add i9 %v0, 1
    #    #  %res0 = icmp ne i9 %v0, (c0? 127: 128)
    #    #  %res1 = icmp eq i9 %v0, (c0? 127: 126)
    #    #  %v2 = select i1 %c0, i9 %v1, i9 %v0
    #    self._test_ll(llvmIr)

    def test_selectSimplify0(self):
        llvmIr = """\
        define void @test_selectSimplify0(ptr addrspace(1) %byte_cnt, ptr addrspace(2) %i) {
        bb0:
          br label %bb1
        
        bb1:
          %byte_cnt1.0 = phi i16 [ 0, %bb0 ], [ %5, %bb1 ]
          %i_read1 = call i19 @hwtHls.streamRead.p2.i64.i19(ptr addrspace(2) %i, i64 16) #4
          %0 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %i_read1, i6 16) #2
          %1 = xor i1 %0, true
          %2 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %i_read1, i6 17) #2
          %3 = xor i1 %2, true
          %brmerge = select i1 %1, i1 true, i1 %3
          %.mux = select i1 %1, i8 0, i8 1
          %iHw64 = trunc i8 %.mux to i2
          %iHw.zext = zext i2 %iHw64 to i8
          %wordByteCnt.0 = select i1 %brmerge, i8 %iHw.zext, i8 2
          %wordByteCnt81 = trunc i8 %wordByteCnt.0 to i2
          %4 = zext i2 %wordByteCnt81 to i16
          %5 = add i16 %byte_cnt1.0, %4
          store volatile i16 %5, ptr addrspace(1) %byte_cnt, align 2
          br label %bb1
        }
        """
        self._test_ll(llvmIr)

        # llvmIr = """\
        # define void @test_selectSimplify0(ptr addrspace(1) %byte_cnt, ptr addrspace(2) %i) {
        # bb0:
        #  br label %bb1
        #
        # bb1:
        #  %byte_cnt1.0 = phi i16 [ 0, %bb0 ], [ %5, %bb1 ]
        #  %i_read1 = call i19 @hwtHls.streamRead.p2.i64.i19(ptr addrspace(2) %i, i64 16) #4
        #  %0 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %i_read1, i6 16) #2
        #  %2 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %i_read1, i6 17) #2
        #  %3 = xor i1 %2, true
        #  %brmerge = select i1 %0, i1 %3, i1 true
        #  %iHw.zext = select i1 %0, i8 1, i8 0
        #  %wordByteCnt.0 = select i1 %brmerge, i8 %iHw.zext, i8 2
        #  %wordByteCnt81 = trunc i8 %wordByteCnt.0 to i2
        #  %4 = zext i2 %wordByteCnt81 to i16
        #  %5 = add i16 %byte_cnt1.0, %4
        #  store volatile i16 %5, ptr addrspace(1) %byte_cnt, align 2
        #  br label %bb1
        # }
        # """

    def test_ctpop_toCtto(self):
        # :note: assume is not directly for strb but for the %0 bits which are src operand of strb slice
        llvmIr = """\
        define void @test_ctpop_toCtto(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          %0 = load volatile i8, ptr addrspace(1) %rx, align 1
          %strb = call i3 @hwtHls.bitRangeGet.i8.i4.i3.0(i8 %0, i4 0) #2
          %strb0 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.0(i8 %0, i4 0) #2
          %strb1 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.1(i8 %0, i4 1) #2
          %strb2 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.2(i8 %0, i4 2) #2
          %prevMaskBit1Impl.0 = icmp ule i1 %strb1, %strb0
          call void @llvm.assume(i1 %prevMaskBit1Impl.0)
          %prevMaskBit1Impl.1 = icmp ule i1 %strb2, %strb1
          call void @llvm.assume(i1 %prevMaskBit1Impl.1)
          %ct = call i3 @llvm.ctpop.i3(i3 %strb)
          store volatile i3 %ct, ptr addrspace(2) %tx, align 1
          ret void
        }
        """
        self._test_ll(llvmIr)

if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HwtHlsInstCombinePass_TC('test_tryReducePopcnt_toCTLO')])
    suite = testLoader.loadTestsFromTestCase(HwtHlsInstCombinePass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
