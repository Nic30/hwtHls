#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class SimplifyCFG2Pass_streamWrite_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return llvm._testSimplifyCFG2Pass(*args, **kwargs)

    # def test_streamWriteMerge0(self):
    #    # writesExit has a linear sequence of predecessors containing only streamWrite
    #    llvmIr = """\
    #    define void @streamWriteMerge0(ptr addrspace(1) %maskIn, ptr addrspace(2) %tx) {
    #    bb0:
    #      br label %bb.pktLoop
    #
    #    bb.pktLoop:
    #      %m0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
    #      %m1.0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
    #      %m1 = and i1 %m0, %m1.0
    #      %eof = load volatile i1, ptr addrspace(1) %maskIn, align 1
    #      br i1 %m0, label %bb.w0, label %bb.writesExit
    #
    #    bb.w0:
    #      call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 1, i1 %eof) #4
    #      br i1 %m1, label %bb.w1, label %bb.writesExit
    #
    #    bb.w1:
    #      call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 2, i1 %eof) #4
    #      br label %bb.writesExit
    #
    #    bb.writesExit:
    #      br label %bb.pktLoop
    #    }
    #    """
    #    self._test_ll(llvmIr)
    #
    def test_streamWriteMerge1(self):
        llvmIr = """\
        define void @streamWriteMerge1(ptr addrspace(1) %maskIn, ptr addrspace(2) %tx) {
        bb0:
          br label %bb.pktLoop
        
        bb.pktLoop:
          %m0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
          %m1.0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
          %m1 = and i1 %m0, %m1.0
          %eof = load volatile i1, ptr addrspace(1) %maskIn, align 1
          br i1 %m0, label %bb.w0, label %bb.w0.exit
        bb.w0:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 1, i1 %eof) #4
          br label %bb.w0.exit 
        bb.w0.exit:
          br i1 %m1, label %bb.w1, label %bb.writesExit
        bb.w1:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 2, i1 %eof) #4
          br label %bb.writesExit
        
        bb.writesExit:
          br label %bb.pktLoop
        }
        """
        self._test_ll(llvmIr)

    def test_streamWriteMerge2(self):
        # same as test_streamWriteMerge1 but first write is not conditional
        llvmIr = """\
        define void @streamWriteMerge2(ptr addrspace(1) %maskIn, ptr addrspace(2) %tx) {
        bb0:
          br label %bb.pktLoop
        
        bb.pktLoop:
          %m0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
          %m1.0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
          %m1 = and i1 %m0, %m1.0
          %eof = load volatile i1, ptr addrspace(1) %maskIn, align 1
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 1, i1 %eof) #4
          br i1 %m1, label %bb.w1, label %bb.writesExit
        bb.w1:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 2, i1 %eof) #4
          br label %bb.writesExit
        
        bb.writesExit:
          br label %bb.pktLoop
        }
        """
        self._test_ll(llvmIr)

    def test_streamWriteMerge3(self):
        llvmIr = """\
        define void @streamWriteMerge3(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %loop.pkt
        
        loop.pkt:
          call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #4
          br label %loop.pkt.read
        
        loop.pkt.read:
          %curLen.015 = phi i11 [ 0, %loop.pkt ], [ %curLen.116.2, %bb.writeExit ]
          %.w0 = load volatile i28, ptr addrspace(1) %rx, align 4
          %0 = call i24 @hwtHls.bitRangeGet.i28.i6.i24.0(i28 %.w0, i6 0) #2
          %1 = call i3 @hwtHls.bitRangeGet.i28.i6.i3.24(i28 %.w0, i6 24) #2
          %2 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %.w0, i6 27) #2
          %3 = call i28 @hwtHls.bitConcat.i24.i3.i1(i24 %0, i3 %1, i1 %2) #2
          %4 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.16(i28 %3, i6 16) #2
          %5 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.26(i28 %3, i6 26) #2
          %6 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.8(i28 %3, i6 8) #2
          %7 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.25(i28 %3, i6 25) #2
          %8 = xor i1 %7, true
          %9 = and i1 %2, %8
          %write0.en = icmp ne i11 %curLen.015, -648
          %10 = icmp eq i11 %curLen.015, -649
          %11 = xor i1 %5, true
          %12 = and i1 %2, %11
          %sig_7.1 = or i1 %12, %10
          %.025 = and i1 %write0.en, %sig_7.1
          %14 = icmp eq i11 %curLen.015, -649
          %15 = add i11 %curLen.015, 2
          %curLen.116.1 = select i1 %write0.en, i11 %15, i11 -648
          %sig_7.2 = or i1 %2, %14
          %.031 = and i1 %write0.en, %sig_7.2
          %sig_8.2 = zext i1 %write0.en to i11
          %curLen.116.2 = add i11 %curLen.116.1, %sig_8.2
          %16 = xor i1 %9, true
          %17 = xor i1 %12, true
          %18 = and i1 %16, %17
          %write2.en = and i1 %18, %write0.en
          %eof.2 = and i1 %18, %.031
          %19 = or i1 %9, %12
          %.230 = select i1 %19, i8 undef, i8 %4
          %write1.en = and i1 %write0.en, %16
          %eof.1 = and i1 %.025, %16
          %.2 = select i1 %9, i8 undef, i8 %6
          %20 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.0(i28 %.w0, i6 0) #2
          %sig_7 = or i1 %9, %10
          br i1 %write0.en, label %bb.write0, label %bb.write1.guard
        
        bb.write0:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %20, i1 %sig_7) #4
          br label %bb.write1.guard
        
        bb.write1.guard:
          br i1 %write1.en, label %bb.write1, label %bb.write2.guard
        
        bb.write1:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %.2, i1 %eof.1) #4
          br label %bb.write2.guard
        
        bb.write2.guard:
          br i1 %write2.en, label %bb.write2, label %bb.writeExit
        
        bb.write2:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %.230, i1 %eof.2) #4
          br label %bb.writeExit
        
        bb.writeExit:
          br i1 %2, label %bb.writeExit.1, label %loop.pkt.read
        
        bb.writeExit.1:
          call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #4
          br label %loop.pkt
        }
        """
        self._test_ll(llvmIr)

    def test_streamWriteMerge_onProductOf_SimplifyBranchOnICmpChain(self):
        # SimplifyBranchOnICmpChain produces specific type of switch which replaces
        # ORs in original condition and produces switch.early.test
        llvmIr = """\
        define void @streamWriteMerge_onProductOf_SimplifyBranchOnICmpChain(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %loop.pkt
        
        loop.pkt:
          %wEn = load volatile i3, ptr addrspace(1) %rx, align 4
          %wEn.0 = icmp ne i3 %wEn, 0
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 1, i1 0) #4
          br i1 %wEn.0, label %switch.early.test, label %loop.pkt.latch
        
        switch.early.test:
          switch i3 %wEn, label %bb.write1 [
            i3 2, label %loop.pkt.latch
            i3 1, label %loop.pkt.latch
          ]
        
        bb.write1:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 2, i1 1) #4
          br label %loop.pkt.latch
        
        loop.pkt.latch:
          br label %loop.pkt
        }
        """
        self._test_ll(llvmIr)

    def test_streamWriteMerge_implicationAssumes0(self):
        # Axi4SPacketTrimByteByByte2 at 4B
        # * all 4 streamWrite should be merged into one
        # * ctpop(x) should become ctlz(~x)
        llvmIr = """\
        define void @streamWriteMerge_implicationAssumes0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %loop.pkt
        
        loop.pkt:
          br label %loop.pkt.read
        
        loop.pkt.read:
          %curLen.0 = phi i9 [ 0, %loop.pkt ], [ %21, %loop.pkt.lastCheck ]
          %.w0 = load volatile i37, ptr addrspace(1) %rx, align 8
          %0 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %.w0, i7 35) #2
          %1 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.34(i37 %.w0, i7 34) #2
          %2 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %.w0, i7 32) #2
          %3 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.w0, i7 33) #2
          %4 = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %.w0, i7 32) #2
          %data.3.0 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.24(i37 %.w0, i7 24) #2
          %6 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.16(i37 %.w0, i7 16) #2
          %7 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.8(i37 %.w0, i7 8) #2
          %rx.last = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.w0, i7 36) #2
          %data.0 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.0(i37 %.w0, i7 0) #2
          %prevMaskBit1Impl = icmp ule i1 %3, %2
          call void @llvm.assume(i1 %prevMaskBit1Impl)
          %prevMaskBit1Impl42 = icmp ule i1 %1, %3
          call void @llvm.assume(i1 %prevMaskBit1Impl42)
          %prevMaskBit1Impl43 = icmp ule i1 %0, %1
          call void @llvm.assume(i1 %prevMaskBit1Impl43)
          %10 = xor i1 %3, true
          %11 = and i1 %rx.last, %10
          %12 = icmp eq i9 %curLen.0, 127
          %13 = or i1 %11, %12
          %eof.0 = and i1 %2, %13
          %14 = xor i1 %1, true
          %15 = and i1 %rx.last, %14
          %16 = xor i1 %0, true
          %17 = and i1 %rx.last, %16
          %18 = call i4 @llvm.ctpop.i4(i4 %4)
          %19 = zext i4 %18 to i9
          %curLen.1 = add i9 %curLen.0, %19
          %21 = call i9 @llvm.umin.i9(i9 %curLen.1, i9 127)
          %22 = icmp eq i9 %curLen.1, 127
          %23 = or i1 %15, %22
          %24 = icmp ne i9 %curLen.1, 128
          %writeEn3.1 = and i1 %3, %24
          %.025 = and i1 %writeEn3.1, %23
          %25 = or i1 %17, %22
          %writeEn3.2 = and i1 %1, %24
          %.031 = and i1 %writeEn3.2, %25
          %26 = or i1 %rx.last, %22
          %writeEn3.3 = and i1 %0, %24
          %.037 = and i1 %writeEn3.3, %26
          %27 = xor i1 %11, true
          %28 = xor i1 %15, true
          %29 = xor i1 %17, true
          %30 = and i1 %27, %28
          %31 = and i1 %30, %29
          %.streamWrite.en21.2 = and i1 %31, %writeEn3.3
          %eof.3 = and i1 %31, %.037
          %32 = or i1 %11, %15
          %33 = or i1 %32, %17
          %data.3 = select i1 %33, i8 undef, i8 %data.3.0
          %.streamWrite.en19.2 = and i1 %30, %writeEn3.2
          %eof.2 = and i1 %30, %.031
          %.230 = select i1 %32, i8 undef, i8 %6
          %eof.1 = and i1 %27, %.025
          %data.1 = select i1 %11, i8 undef, i8 %7
          br i1 %2, label %bb.w0, label %bb.w1.guard
        
        bb.w0:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %data.0, i1 %eof.0) #4
          br label %bb.w1.guard
        
        bb.w1.guard:
          br i1 %writeEn3.1, label %bb.w1, label %bb.w2.guard
        
        bb.w1:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %data.1, i1 %eof.1) #4
          br label %bb.w2.guard
        
        bb.w2.guard:
          br i1 %.streamWrite.en19.2, label %bb.w2, label %bb.w3.guard
        
        bb.w2:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %.230, i1 %eof.2) #4
          br label %bb.w3.guard
        
        bb.w3.guard:
          br i1 %.streamWrite.en21.2, label %bb.w3, label %loop.pkt.lastCheck
        
        bb.w3:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %data.3, i1 %eof.3) #4
          br label %loop.pkt.lastCheck
        
        loop.pkt.lastCheck:
          br i1 %rx.last, label %loop.pkt.eof, label %loop.pkt.read
        
        loop.pkt.eof:
          br label %loop.pkt
        }
        """
        self._test_ll(llvmIr)

    def test_streamWriteMerge_implicationAssumes1(self):
        # Axi4SPacketTrimByteByByte2 at 4B
        # * all 4 streamWrite should be merged into one
        # * ctpop(x) should become ctlz(~x)
        llvmIr = """\
        define void @streamWriteMerge_implicationAssumes1(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %loop.pkt
        
        loop.pkt:
          br label %loop.pkt.read
        
        loop.pkt.read:
          %curLen.013 = phi i9 [ 0, %loop.pkt ], [ %44, %loop.pkt.lastCheck.6.writesExit ]
          %.w0 = load volatile i64, ptr addrspace(1) %rx, align 8
          %0 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.63(i64 %.w0, i7 63) #2
          %1 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.62(i64 %.w0, i7 62) #2
          %2 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.61(i64 %.w0, i7 61) #2
          %3 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.60(i64 %.w0, i7 60) #2
          %4 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.59(i64 %.w0, i7 59) #2
          %5 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.58(i64 %.w0, i7 58) #2
          %6 = call i56 @hwtHls.bitRangeGet.i64.i7.i56.0(i64 %.w0, i7 0) #2
          %7 = call i7 @hwtHls.bitRangeGet.i64.i7.i7.56(i64 %.w0, i7 56) #2
          %8 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.56(i64 %.w0, i7 56) #2
          %9 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.57(i64 %.w0, i7 57) #2
          %prevMaskBit1Impl74 = icmp ule i1 %9, %8
          call void @llvm.assume(i1 %prevMaskBit1Impl74)
          %prevMaskBit1Impl75 = icmp ule i1 %5, %9
          call void @llvm.assume(i1 %prevMaskBit1Impl75)
          %prevMaskBit1Impl76 = icmp ule i1 %4, %5
          call void @llvm.assume(i1 %prevMaskBit1Impl76)
          %prevMaskBit1Impl77 = icmp ule i1 %3, %4
          call void @llvm.assume(i1 %prevMaskBit1Impl77)
          %prevMaskBit1Impl78 = icmp ule i1 %2, %3
          call void @llvm.assume(i1 %prevMaskBit1Impl78)
          %prevMaskBit1Impl79 = icmp ule i1 %1, %2
          call void @llvm.assume(i1 %prevMaskBit1Impl79)
          %10 = call i64 @hwtHls.bitConcat.i56.i7.i1(i56 %6, i7 %7, i1 %0) #2
          %11 = call i7 @hwtHls.bitRangeGet.i64.i7.i7.56(i64 %10, i7 56) #2
          %12 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.48(i64 %10, i7 48) #2
          %13 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.40(i64 %10, i7 40) #2
          %14 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.32(i64 %10, i7 32) #2
          %15 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.24(i64 %10, i7 24) #2
          %16 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.16(i64 %10, i7 16) #2
          %17 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.8(i64 %10, i7 8) #2
          %18 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.0(i64 %10, i7 0) #2
          %19 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.63(i64 %10, i7 63) #2
          %20 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.62(i64 %10, i7 62) #2
          %21 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.61(i64 %10, i7 61) #2
          %22 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.60(i64 %10, i7 60) #2
          %23 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.59(i64 %10, i7 59) #2
          %24 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.58(i64 %10, i7 58) #2
          %25 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.56(i64 %10, i7 56) #2
          %26 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.57(i64 %10, i7 57) #2
          %prevMaskBit1Impl = icmp ule i1 %26, %25
          call void @llvm.assume(i1 %prevMaskBit1Impl)
          %prevMaskBit1Impl65 = icmp ule i1 %24, %26
          call void @llvm.assume(i1 %prevMaskBit1Impl65)
          %prevMaskBit1Impl66 = icmp ule i1 %23, %24
          call void @llvm.assume(i1 %prevMaskBit1Impl66)
          %prevMaskBit1Impl67 = icmp ule i1 %22, %23
          call void @llvm.assume(i1 %prevMaskBit1Impl67)
          %prevMaskBit1Impl68 = icmp ule i1 %21, %22
          call void @llvm.assume(i1 %prevMaskBit1Impl68)
          %prevMaskBit1Impl69 = icmp ule i1 %20, %21
          call void @llvm.assume(i1 %prevMaskBit1Impl69)
          %27 = xor i1 %26, true
          %28 = and i1 %19, %27
          %29 = icmp eq i9 %curLen.013, 127
          %30 = or i1 %28, %29
          %.029 = and i1 %25, %30
          %31 = xor i1 %24, true
          %32 = and i1 %19, %31
          %33 = xor i1 %23, true
          %34 = and i1 %19, %33
          %35 = xor i1 %22, true
          %36 = and i1 %19, %35
          %37 = xor i1 %21, true
          %38 = and i1 %19, %37
          %39 = xor i1 %20, true
          %40 = and i1 %19, %39
          %41 = call i7 @llvm.ctpop.i7(i7 %11)
          %42 = zext i7 %41 to i9
          %curLen.114.6 = add i9 %curLen.013, %42
          %44 = call i9 @llvm.umin.i9(i9 %curLen.114.6, i9 127)
          %45 = icmp eq i9 %curLen.114.6, 127
          %46 = or i1 %32, %45
          %47 = icmp ne i9 %curLen.114.6, 128
          %writeEn3.1 = and i1 %26, %47
          %.031 = and i1 %writeEn3.1, %46
          %48 = or i1 %34, %45
          %writeEn3.2 = and i1 %24, %47
          %.037 = and i1 %writeEn3.2, %48
          %49 = or i1 %36, %45
          %writeEn3.3 = and i1 %23, %47
          %.043 = and i1 %writeEn3.3, %49
          %50 = or i1 %38, %45
          %writeEn3.4 = and i1 %22, %47
          %.049 = and i1 %writeEn3.4, %50
          %51 = or i1 %40, %45
          %writeEn3.5 = and i1 %21, %47
          %.055 = and i1 %writeEn3.5, %51
          %52 = or i1 %19, %45
          %writeEn3.6 = and i1 %20, %47
          %.061 = and i1 %writeEn3.6, %52
          %53 = xor i1 %28, true
          %54 = xor i1 %32, true
          %55 = xor i1 %34, true
          %56 = xor i1 %36, true
          %57 = xor i1 %38, true
          %58 = xor i1 %40, true
          %59 = and i1 %53, %54
          %60 = and i1 %59, %55
          %61 = and i1 %60, %56
          %62 = and i1 %61, %57
          %63 = and i1 %62, %58
          %.streamWrite.en27.2 = and i1 %63, %writeEn3.6
          %.263 = and i1 %63, %.061
          %64 = or i1 %28, %32
          %65 = or i1 %64, %34
          %66 = or i1 %65, %36
          %67 = or i1 %66, %38
          %68 = or i1 %67, %40
          %.260 = select i1 %68, i8 undef, i8 %12
          %.streamWrite.en25.2 = and i1 %62, %writeEn3.5
          %.257 = and i1 %62, %.055
          %.254 = select i1 %67, i8 undef, i8 %13
          %.streamWrite.en23.2 = and i1 %61, %writeEn3.4
          %.251 = and i1 %61, %.049
          %.248 = select i1 %66, i8 undef, i8 %14
          %.streamWrite.en21.2 = and i1 %60, %writeEn3.3
          %.245 = and i1 %60, %.043
          %.242 = select i1 %65, i8 undef, i8 %15
          %.streamWrite.en19.2 = and i1 %59, %writeEn3.2
          %.239 = and i1 %59, %.037
          %.236 = select i1 %64, i8 undef, i8 %16
          %.233 = and i1 %53, %.031
          %.2 = select i1 %28, i8 undef, i8 %17
          %loopExitCond = or i1 %68, %19
          %69 = or i1 %25, %writeEn3.1
          %70 = or i1 %69, %.streamWrite.en19.2
          %71 = or i1 %70, %.streamWrite.en21.2
          %72 = or i1 %71, %.streamWrite.en23.2
          %73 = or i1 %72, %.streamWrite.en25.2
          %74 = call i48 @hwtHls.bitConcat.i8.i8.i8.i8.i8.i8(i8 %18, i8 %.2, i8 %.236, i8 %.242, i8 %.248, i8 %.254) #2
          %75 = call i6 @hwtHls.bitConcat.i1.i1.i1.i1.i1.i1(i1 %25, i1 %writeEn3.1, i1 %.streamWrite.en19.2, i1 %.streamWrite.en21.2, i1 %.streamWrite.en23.2, i1 %.streamWrite.en25.2) #2
          %76 = or i1 %.029, %.233
          %77 = or i1 %76, %.239
          %78 = or i1 %77, %.245
          %79 = or i1 %78, %.251
          %80 = or i1 %79, %.257
          br i1 %73, label %loop.pkt.write.5.streamWrite.sinked, label %81
        
        loop.pkt.write.5.streamWrite.sinked:
          call void @hwtHls.streamWrite.masked.p2.i48.i6.i1(ptr addrspace(2) %tx, i48 %74, i6 %75, i1 %80) #4
          br label %81
        
        81:
          br i1 %.streamWrite.en27.2, label %loop.pkt.write.6.streamWrite.sinked, label %loop.pkt.lastCheck.6.writesExit
        
        loop.pkt.write.6.streamWrite.sinked:
          call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %.260, i1 %.263) #4
          br label %loop.pkt.lastCheck.6.writesExit
        
        loop.pkt.lastCheck.6.writesExit:
          br i1 %loopExitCond, label %loop.pkt.eof, label %loop.pkt.read
        
        loop.pkt.eof:
          br label %loop.pkt
        }
        """
        self._test_ll(llvmIr)

    def test_streamWriteMerge_implicationAssumes2(self):
        # originally Axi4SPacketTrimByteByByte4 @ 4B
        llvmIr = """\
define void @test_streamWriteMerge_implicationAssumes2(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %loop.pkt.read

loop.pkt.read:
  %curLen.013 = phi i9 [ 0, %loop.pkt ], [ %25, %loop.pkt.lastCheck.3.writesExit ]
  %.w0 = load volatile i37, ptr addrspace(1) %rx, align 8
  %0 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %.w0, i7 35) #2
  %1 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.34(i37 %.w0, i7 34) #2
  %2 = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %.w0, i7 32) #2
  %3 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %.w0, i7 32) #2
  %4 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.w0, i7 36) #2
  %5 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.w0, i7 33) #2
  %prevMaskBit1Impl46 = icmp ule i1 %5, %3
  call void @llvm.assume(i1 %prevMaskBit1Impl46)
  %maskBitNonLastImpl47 = or i1 %4, %5
  call void @llvm.assume(i1 %maskBitNonLastImpl47)
  %prevMaskBit1Impl48 = icmp ule i1 %1, %5
  call void @llvm.assume(i1 %prevMaskBit1Impl48)
  %maskBitNonLastImpl49 = or i1 %4, %1
  call void @llvm.assume(i1 %maskBitNonLastImpl49)
  %prevMaskBit1Impl50 = icmp ule i1 %0, %1
  call void @llvm.assume(i1 %prevMaskBit1Impl50)
  %maskBitNonLastImpl51 = or i1 %4, %0
  call void @llvm.assume(i1 %maskBitNonLastImpl51)
  %6 = icmp eq i4 %2, -1
  %maskAll1ifLastImpl52 = or i1 %4, %6
  call void @llvm.assume(i1 %maskAll1ifLastImpl52)
  %7 = call i16 @hwtHls.bitRangeGet.i37.i7.i16.0(i37 %.w0, i7 0) #2
  %8 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.24(i37 %.w0, i7 24) #2
  %9 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.16(i37 %.w0, i7 16) #2
  %10 = xor i1 %5, true
  %11 = and i1 %4, %10
  %12 = icmp ult i9 %curLen.013, 128
  %wEn3 = and i1 %3, %12
  %13 = icmp eq i9 %curLen.013, 127
  %14 = or i1 %11, %13
  %.023 = and i1 %wEn3, %14
  %15 = xor i1 %1, true
  %16 = and i1 %4, %15
  %17 = xor i4 %2, -1
  %18 = call i4 @llvm.cttz.i4(i4 %17, i1 false)
  %19 = zext i4 %18 to i10
  %20 = zext i9 %curLen.013 to i10
  %21 = add nuw i10 %20, %19
  %22 = xor i1 %0, true
  %23 = and i1 %4, %22
  %24 = call i10 @llvm.umin.i10(i10 %21, i10 128)
  %25 = trunc i10 %24 to i9
  %26 = icmp eq i10 %21, 127
  %27 = or i1 %16, %26
  %28 = icmp ult i10 %21, 128
  %wEn3.1 = and i1 %5, %28
  %.025 = and i1 %wEn3.1, %27
  %29 = or i1 %23, %26
  %wEn3.2 = and i1 %1, %28
  %.031 = and i1 %wEn3.2, %29
  %30 = or i1 %4, %26
  %wEn3.3 = and i1 %0, %28
  %.037 = and i1 %wEn3.3, %30
  %31 = xor i1 %11, true
  %32 = xor i1 %16, true
  %33 = xor i1 %23, true
  %34 = and i1 %31, %32
  %35 = and i1 %34, %33
  %.streamWrite.en21.2 = and i1 %35, %wEn3.3
  %.239 = and i1 %35, %.037
  %.streamWrite.en19.2 = and i1 %34, %wEn3.2
  %.233 = and i1 %34, %.031
  %.227 = and i1 %31, %.025
  %36 = or i1 %wEn3, %wEn3.1
  %37 = call i2 @hwtHls.bitConcat.i1.i1(i1 %wEn3, i1 %wEn3.1) #2
  %38 = or i1 %.023, %.227
  br i1 %36, label %loop.pkt.write.1, label %loop.pkt.write.2.guard

loop.pkt.write.1:
  call void @hwtHls.streamWrite.masked.p2.i16.i2.i1(ptr addrspace(2) %tx, i16 %7, i2 %37, i1 %38) #4
  br label %loop.pkt.write.2.guard

loop.pkt.write.2.guard:
  br i1 %.streamWrite.en19.2, label %loop.pkt.write.2, label %loop.pkt.write.3.guard

loop.pkt.write.2:
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %9, i1 %.233) #4
  br label %loop.pkt.write.3.guard

loop.pkt.write.3.guard:
  %impCache = icmp ule i1 %wEn3.1, %wEn3
  br i1 %.streamWrite.en21.2, label %loop.pkt.write.3, label %loop.pkt.lastCheck.3.writesExit

loop.pkt.write.3:
  call void @llvm.assume(i1 %impCache)
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %8, i1 %.239) #4
  br label %loop.pkt.lastCheck.3.writesExit

loop.pkt.lastCheck.3.writesExit:
  br i1 %4, label %loop.pkt.eof, label %loop.pkt.read

loop.pkt.eof:
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %loop.pkt
}
        """
        self._test_ll(llvmIr)

    def test_streamWriteMerge_implicationAssumes3(self):
        # originally Axi4SPacketTrimByteByByte4 @ 3B
        llvmIr = """\
define void @test_streamWriteMerge_implicationAssumes3(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %loop.pkt.read

loop.pkt.read:
  %curLen.013 = phi i9 [ 0, %loop.pkt ], [ %23, %loop.pkt.lastCheck.2.writesExit ]
  %.w0 = load volatile i28, ptr addrspace(1) %rx, align 4
  %0 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.24(i28 %.w0, i6 24) #2
  %1 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.26(i28 %.w0, i6 26) #2
  %2 = call i3 @hwtHls.bitRangeGet.i28.i6.i3.24(i28 %.w0, i6 24) #2
  %3 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.24(i28 %.w0, i6 24) #2
  %4 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %.w0, i6 27) #2
  %5 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.25(i28 %.w0, i6 25) #2
  %prevMaskBit1Impl35 = icmp ule i1 %5, %3
  call void @llvm.assume(i1 %prevMaskBit1Impl35)
  %maskBitNonLastImpl36 = or i1 %4, %5
  call void @llvm.assume(i1 %maskBitNonLastImpl36)
  %prevMaskBit1Impl37 = icmp ule i1 %1, %5
  call void @llvm.assume(i1 %prevMaskBit1Impl37)
  %6 = icmp eq i2 %0, -1
  %prevMaskBitAll1Impl38 = icmp ule i1 %1, %6
  call void @llvm.assume(i1 %prevMaskBitAll1Impl38)
  %maskBitNonLastImpl39 = or i1 %4, %1
  call void @llvm.assume(i1 %maskBitNonLastImpl39)
  %7 = icmp eq i3 %2, -1
  %maskAll1ifLastImpl40 = or i1 %4, %7
  call void @llvm.assume(i1 %maskAll1ifLastImpl40)
  %8 = call i16 @hwtHls.bitRangeGet.i28.i6.i16.0(i28 %.w0, i6 0) #2
  %9 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.16(i28 %.w0, i6 16) #2
  %10 = xor i1 %5, true
  %11 = and i1 %4, %10
  %12 = icmp ult i9 %curLen.013, 128
  %wEn3 = and i1 %3, %12
  %13 = icmp eq i9 %curLen.013, 127
  %14 = or i1 %11, %13
  %.021 = and i1 %wEn3, %14
  %15 = xor i1 %1, true
  %16 = and i1 %4, %15
  %17 = xor i3 %2, -1
  %18 = call i3 @llvm.cttz.i3(i3 %17, i1 false)
  %19 = zext i3 %18 to i10
  %20 = zext i9 %curLen.013 to i10
  %21 = add nuw i10 %20, %19
  %22 = call i10 @llvm.umin.i10(i10 %21, i10 128)
  %23 = trunc i10 %22 to i9
  %24 = icmp eq i10 %21, 127
  %25 = or i1 %16, %24
  %26 = icmp ult i10 %21, 128
  %wEn3.1 = and i1 %5, %26
  %.023 = and i1 %wEn3.1, %25
  %27 = or i1 %4, %24
  %wEn3.2 = and i1 %1, %26
  %.029 = and i1 %wEn3.2, %27
  %28 = xor i1 %11, true
  %29 = xor i1 %16, true
  %30 = and i1 %28, %29
  %.streamWrite.en19.2 = and i1 %30, %wEn3.2
  %.231 = and i1 %30, %.029
  %.225 = and i1 %28, %.023
  %31 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %wEn3.1) #2
  %32 = or i1 %.021, %.225
  br i1 %wEn3, label %loop.pkt.write.1.streamWrite.sinked, label %33

loop.pkt.write.1.streamWrite.sinked:
  call void @hwtHls.streamWrite.masked.p2.i16.i2.i1(ptr addrspace(2) %tx, i16 %8, i2 %31, i1 %32) #4
  br label %33

33:
  %impCache = icmp ule i1 %wEn3.1, %wEn3
  br i1 %.streamWrite.en19.2, label %loop.pkt.write.2.streamWrite.sinked, label %loop.pkt.lastCheck.2.writesExit

loop.pkt.write.2.streamWrite.sinked:
  call void @llvm.assume(i1 %impCache)
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %9, i1 %.231) #4
  br label %loop.pkt.lastCheck.2.writesExit

loop.pkt.lastCheck.2.writesExit:
  br i1 %4, label %loop.pkt.eof, label %loop.pkt.read

loop.pkt.eof:
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %loop.pkt
}
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    #suite = unittest.TestSuite([SimplifyCFG2Pass_streamWrite_TC('test_streamWriteMerge_implicationAssumes0')])
    suite = testLoader.loadTestsFromTestCase(SimplifyCFG2Pass_streamWrite_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
