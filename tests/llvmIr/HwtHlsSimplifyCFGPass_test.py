#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function, verifyFunction, StringRef
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class HwtHlsSimplifyCFGPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        # def printOnChange(ruleName: StringRef, F: Function):
        #     print("after ", ruleName.str())
        #     print(F)
        # 
        # llvm._dbgIrInstrCombineChangeCallbackFn = printOnChange
        # llvm._dbgIrCfgSimplifyChangeCallbackFn = printOnChange
        
        
        F = llvm._testHwtHlsSimplifyCFGPass(*args, **kwargs)
        assert not verifyFunction(F)
        return F

    def test_loadMerge(self):
        llvmIr = """\
        define void @loadMerge(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        loadMerge:
          br label %bb0_sw
        
        bb0_sw:
          %i0.w0 = load volatile i17, ptr addrspace(1) %i, align 4
          %0 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i0.w0, i6 0) #2
          %1 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i0.w0, i6 16) #2
          %i0 = call i17 @hwtHls.bitConcat.i16.i1(i16 %0, i1 %1) #2
          %2 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i0, i6 0) #2
          switch i16 %2, label %bb0_sw_def [
            i16 3, label %bb0_sw_case3
            i16 4, label %bb0_sw_case4
          ]
        
        bb0_sw_case3:
          %i1.w0 = load volatile i17, ptr addrspace(1) %i, align 4
          %3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i1.w0, i6 0) #2
          %4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i1.w0, i6 16) #2
          %i1.w1 = load volatile i17, ptr addrspace(1) %i, align 4
          %5 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %i1.w1, i6 0) #2
          %6 = call i24 @hwtHls.bitConcat.i16.i8(i16 %3, i8 %5) #2
          %i1 = call i25 @hwtHls.bitConcat.i24.i1(i24 %6, i1 %4) #2
          %7 = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %i1, i6 0) #2
          %8 = zext i24 %7 to i32
          store volatile i32 %8, ptr addrspace(2) %o, align 4
          br label %bb0_sw_def
        
        bb0_sw_def:
          %iDataOffset.1 = phi i1 [ true, %bb0_sw ], [ true, %bb0_sw_case4 ], [ %4, %bb0_sw_case3 ]
          br i1 %iDataOffset.1, label %bb_opt_ld, label %ioff0
        
        bb_opt_ld:
          %i3.opt = load volatile i17, ptr addrspace(1) %i, align 4
          br label %ioff0
        
        ioff0:
          br label %bb0_sw
        
        bb0_sw_case4:
          %i2.w0 = load volatile i17, ptr addrspace(1) %i, align 4
          %9 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i2.w0, i6 0) #2
          %10 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i2.w0, i6 16) #2
          %i2.w1 = load volatile i17, ptr addrspace(1) %i, align 4
          %11 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i2.w1, i6 0) #2
          %12 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i2.w1, i6 16) #2
          %13 = call i32 @hwtHls.bitConcat.i16.i16(i16 %9, i16 %11) #2
          %14 = or i1 %10, %12
          %i3 = call i33 @hwtHls.bitConcat.i32.i1(i32 %13, i1 %14) #2
          %15 = call i32 @hwtHls.bitRangeGet.i33.i7.i32.0(i33 %i3, i7 0) #2
          store volatile i32 %15, ptr addrspace(2) %o, align 4
          br label %bb0_sw_def
        }
        """
        self._test_ll(llvmIr, passKwArgs=dict(
                          ForwardSwitchCondToPhi=True,
                          ConvertSwitchRangeToICmp=True,
                          NeedCanonicalLoops=False,
                          HoistCommonInsts=True,
                          SinkCommonInsts=True,
                          HoistCheapInsts=True
                      ))

    def test_optionalStore0(self):
        llvmIr = """\
        define void @optionalStore0(ptr addrspace(1) %o) {
        entry:
          br label %bb0
        
        bb0:
          %i = phi i1 [ false, %entry ], [ %"i.not", %bb2 ]
          store volatile i8 1, ptr addrspace(1) %o, align 1
          br i1 %i, label %bb2, label %bb1
        
        bb1: 
          store volatile i8 2, ptr addrspace(1) %o, align 1
          br label %bb2
        
        bb2:
          %"i.not" = xor i1 %i, true
          store volatile i8 3, ptr addrspace(1) %o, align 1
          br label %bb0
        }
        """
        self._test_ll(llvmIr)

    def test_loopHeaderPhisNotExtended(self):
        # this test test that the phis in loop headers are not getting new incoming values.
        # because if loop has phi with more than 2 incoming values it would get split into multiple loops
        # which would make any later optimization significantly harder
        # :note: based on ExampleCam.updateThread
        llvmIr = """\
        define void @loopHeaderPhisNotExtended(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %write) {
        bb0:
          br label %bb.header
        
        bb.header:
          %k3_key.0 = phi i16 [ undef, %bb0 ], [ %k3_key.1, %bb.sw_setSwEnd ]
          %k2_key.0 = phi i16 [ undef, %bb0 ], [ %k2_key.1, %bb.sw_setSwEnd ]
          %k1_key.0 = phi i16 [ undef, %bb0 ], [ %k1_key.1, %bb.sw_setSwEnd ]
          %k0_key.0 = phi i16 [ undef, %bb0 ], [ %k0_key.1, %bb.sw_setSwEnd ]
          %k0_vld.018 = phi i1 [ false, %bb0 ], [ %k0_vld.119, %bb.sw_setSwEnd ]
          %k1_vld.020 = phi i1 [ false, %bb0 ], [ %k1_vld.121, %bb.sw_setSwEnd ]
          %k2_vld.022 = phi i1 [ false, %bb0 ], [ %k2_vld.123, %bb.sw_setSwEnd ]
          %k3_vld.024 = phi i1 [ false, %bb0 ], [ %k3_vld.125, %bb.sw_setSwEnd ]
          %0 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k0_key.0, i1 %k0_vld.018) #2
          store volatile i17 %0, ptr addrspace(1) %keyForMatchThread_0, align 4
          %1 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k1_key.0, i1 %k1_vld.020) #2
          store volatile i17 %1, ptr addrspace(2) %keyForMatchThread_1, align 4
          %2 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k2_key.0, i1 %k2_vld.022) #2
          store volatile i17 %2, ptr addrspace(3) %keyForMatchThread_2, align 4
          %3 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k3_key.0, i1 %k3_vld.024) #2
          store volatile i17 %3, ptr addrspace(4) %keyForMatchThread_3, align 4
          %write_read = load volatile i19, ptr addrspace(5) %write, align 4
          %4 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %write_read, i6 18) #2
          %5 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.2(i19 %write_read, i6 2) #2
          %6 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19 %write_read, i6 0) #2
          switch i2 %6, label %bb.header.unreachabledefault [
            i2 0, label %bb.sw_setSwEnd
            i2 1, label %bb.sw_c1
            i2 -2, label %bb.sw_c2
            i2 -1, label %bb.sw_c3
          ]
        
        bb.header.unreachabledefault:
          unreachable
        
        bb.sw_c1:
          br label %bb.sw_setSwEnd
        
        bb.sw_c2:
          br label %bb.sw_setSwEnd
        
        bb.sw_c3:
          br label %bb.sw_setSwEnd
        
        bb.sw_setSwEnd:
          %k3_key.1 = phi i16 [ %5, %bb.sw_c3 ], [ %k3_key.0, %bb.sw_c2 ], [ %k3_key.0, %bb.sw_c1 ], [ %k3_key.0, %bb.header ]
          %k2_key.1 = phi i16 [ %k2_key.0, %bb.sw_c3 ], [ %5, %bb.sw_c2 ], [ %k2_key.0, %bb.sw_c1 ], [ %k2_key.0, %bb.header ]
          %k1_key.1 = phi i16 [ %k1_key.0, %bb.sw_c3 ], [ %k1_key.0, %bb.sw_c2 ], [ %5, %bb.sw_c1 ], [ %k1_key.0, %bb.header ]
          %k0_key.1 = phi i16 [ %k0_key.0, %bb.sw_c3 ], [ %k0_key.0, %bb.sw_c2 ], [ %k0_key.0, %bb.sw_c1 ], [ %5, %bb.header ]
          %k0_vld.119 = phi i1 [ %k0_vld.018, %bb.sw_c3 ], [ %k0_vld.018, %bb.sw_c2 ], [ %k0_vld.018, %bb.sw_c1 ], [ %4, %bb.header ]
          %k1_vld.121 = phi i1 [ %k1_vld.020, %bb.sw_c3 ], [ %k1_vld.020, %bb.sw_c2 ], [ %4, %bb.sw_c1 ], [ %k1_vld.020, %bb.header ]
          %k2_vld.123 = phi i1 [ %k2_vld.022, %bb.sw_c3 ], [ %4, %bb.sw_c2 ], [ %k2_vld.022, %bb.sw_c1 ], [ %k2_vld.022, %bb.header ]
          %k3_vld.125 = phi i1 [ %4, %bb.sw_c3 ], [ %k3_vld.024, %bb.sw_c2 ], [ %k3_vld.024, %bb.sw_c1 ], [ %k3_vld.024, %bb.header ]
          br label %bb.header
        }
        """
        self._test_ll(llvmIr)

    def test_PhiToSelect0(self):
        # :note: %curLen.015 is not converted beause it is in loop header
        #        %curLen.116 is not converted because bb0.enabled is not empty
        llvmIr = """\
        define void @PhiToSelect0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
        bb0:
          br label %loop.pkt
        
        loop.pkt:
          br label %loop.pkt.read
        
        loop.pkt.read:
          %curLen.015 = phi i5 [ 0, %loop.pkt ], [ %curLen.116, %loop.pkt.end ]
          %rx_read1.w0 = load volatile i10, ptr addrspace(1) %rx, align 2
          %0 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read1.w0, i5 9) #2
          %sig_.not = icmp eq i5 %curLen.015, 10
          br i1 %sig_.not, label %loop.pkt.end, label %bb0.enabled
        
        bb0.enabled:
          %sig_8 = add i5 %curLen.015, 1
          %sig_6 = icmp eq i5 %curLen.015, 9
          %sig_7 = or i1 %0, %sig_6
          %1 = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read1.w0, i5 0) #2
          %2 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %1, i1 true, i1 %sig_7) #2
          store volatile i10 %2, ptr addrspace(2) %tx, align 2
          br label %loop.pkt.end
        
        loop.pkt.end:
          %curLen.116 = phi i5 [ %sig_8, %bb0.enabled ], [ %curLen.015, %loop.pkt.read ]
          br i1 %0, label %loop.pkt, label %loop.pkt.read
        }
        """
        self._test_ll(llvmIr)

    def test_PhiToSelect1(self):
        # :note: originally Axi4SPacketByteCntr2 @16b
        llvmIr = """\
        define void @test_PhiToSelect1(ptr addrspace(1) %byte_cnt, ptr addrspace(2) %i) {
        bb0:
          br label %bb1
        
        bb1:
          %byte_cnt1.0 = phi i16 [ 0, %bb0 ], [ %5, %bb4 ]
          %i_read1 = load volatile i19, ptr addrspace(2) %i, align 1
          %0 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %i_read1, i6 16) #2
          %1 = xor i1 %0, true
          %2 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %i_read1, i6 17) #2
          %3 = xor i1 %2, true
          br i1 %1, label %bb3, label %bb2
        
        bb2:
          br i1 %3, label %bb3, label %bb4
        
        bb3:
          %iHw.0 = phi i8 [ 0, %bb1 ], [ 1, %bb2 ]
          %iHw64 = trunc i8 %iHw.0 to i2
          %iHw.zext = zext i2 %iHw64 to i8
          br label %bb4
        
        bb4:
          %wordByteCnt.0 = phi i8 [ %iHw.zext, %bb3 ], [ 2, %bb2 ]
          %wordByteCnt81 = trunc i8 %wordByteCnt.0 to i2
          %4 = zext i2 %wordByteCnt81 to i16
          %5 = add i16 %byte_cnt1.0, %4
          store volatile i16 %5, ptr addrspace(1) %byte_cnt, align 2
          br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_noSuboptimalLoopUnswitch(self):
        # llvmIr = """\
        # define void @test_noSuboptimalLoopUnswitch(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        # bb0:
        #   br label %mainLoop
        #
        # mainLoop:                                         ; preds = %bb0, %_forwardPacket.ret
        #   %isChild = phi i1 [ false, %bb0 ], [ %isChildInLatch, %_forwardPacket.ret ]
        #   br i1 %isChild, label %copyLoop, label %mainLoop.split
        #
        # mainLoop.split:                                   ; preds = %mainLoop
        #   %r0 = load volatile i17, ptr addrspace(1) %dataIn, align 4
        #   %r0.last = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %r0, i6 16) #2
        #   %0 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %r0, i6 0) #2
        #   %r1 = zext i8 %0 to i9
        #   %r1.last = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %r1, i5 8) #2
        #   %1 = call i17 @hwtHls.bitConcat.i8.i8.i1(i8 %0, i8 undef, i1 true) #2
        #   %2 = select i1 %r1.last, i17 %1, i17 %r0
        #   store volatile i17 %2, ptr addrspace(2) %dataOut, align 4
        #   %merge = or i1 %r0.last, %r1.last
        #   br i1 %merge, label %_forwardPacket.ret.oldLatch, label %copyLoop
        #
        # copyLoop:                                         ; preds = %mainLoop.split, %mainLoop
        #   %r2 = load volatile i17, ptr addrspace(1) %dataIn, align 4
        #   %r2.last = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %r2, i6 16) #2
        #   %3 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %r2, i6 0) #2
        #   %r3 = zext i8 %3 to i9
        #   %r3.last = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %r3, i5 8) #2
        #   %4 = call i17 @hwtHls.bitConcat.i8.i8.i1(i8 %3, i8 undef, i1 true) #2
        #   %5 = select i1 %r3.last, i17 %4, i17 %r2
        #   store volatile i17 %5, ptr addrspace(2) %dataOut, align 4
        #   %merge2 = or i1 %r2.last, %r3.last
        #   br i1 %merge2, label %_forwardPacket.ret.oldLatch, label %_forwardPacket.ret
        #
        # _forwardPacket.ret.oldLatch:                      ; preds = %copyLoop, %mainLoop.split
        #   br label %_forwardPacket.ret
        #
        # _forwardPacket.ret:                               ; preds = %copyLoop, %_forwardPacket.ret.oldLatch
        #   %isChildInLatch = phi i1 [ true, %copyLoop ], [ false, %_forwardPacket.ret.oldLatch ]
        #   br label %mainLoop
        # }
        # """
        llvmIr = """\
        define void @test_noSuboptimalLoopUnswitch(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb0:
          br label %mainLoop
        
        mainLoop:                                         ; preds = %bb0, %_forwardPacket.ret
          %isChild = phi i1 [ false, %bb0 ], [ %isChildInLatch, %_forwardPacket.ret ]
          br i1 %isChild, label %copyLoop, label %mainLoop.split
        
        mainLoop.split:                                   ; preds = %mainLoop
          %r0 = load volatile i17, ptr addrspace(1) %dataIn, align 4
          %r0.last = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %r0, i6 16) #2
          %0 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %r0, i6 0) #2
          %r1 = zext i8 %0 to i9
          %r1.last = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %r1, i5 8) #2
          %1 = call i17 @hwtHls.bitConcat.i8.i8.i1(i8 %0, i8 undef, i1 true) #2
          %2 = select i1 %r1.last, i17 %1, i17 %r0
          store volatile i17 %2, ptr addrspace(2) %dataOut, align 4
          %merge = or i1 %r0.last, %r1.last
          br i1 %merge, label %_forwardPacket.ret.oldLatch, label %_forwardPacket.ret.oldLatchToChild
        
        copyLoop:                                         ; preds = %mainLoop.split, %mainLoop
          %r2 = load volatile i17, ptr addrspace(1) %dataIn, align 4
          %r2.last = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %r2, i6 16) #2
          %3 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %r2, i6 0) #2
          %r3 = zext i8 %3 to i9
          %r3.last = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %r3, i5 8) #2
          %4 = call i17 @hwtHls.bitConcat.i8.i8.i1(i8 %3, i8 undef, i1 true) #2
          %5 = select i1 %r3.last, i17 %4, i17 %r2
          store volatile i17 %5, ptr addrspace(2) %dataOut, align 4
          %merge2 = or i1 %r2.last, %r3.last
          br i1 %merge2, label %_forwardPacket.ret.oldLatch, label %_forwardPacket.ret
        
        _forwardPacket.ret.oldLatch:                      ; preds = %copyLoop, %mainLoop.split
          br label %_forwardPacket.ret
        
        _forwardPacket.ret.oldLatchToChild:                      ; preds = %copyLoop, %mainLoop.split
          br label %_forwardPacket.ret
        
        _forwardPacket.ret:                               ; preds = %copyLoop, %_forwardPacket.ret.oldLatchToChild ],, %_forwardPacket.ret.oldLatch
          %isChildInLatch = phi i1 [ true, %copyLoop ], [ true, %_forwardPacket.ret.oldLatchToChild ], [ false, %_forwardPacket.ret.oldLatch ]
          br label %mainLoop
        }
        """
        self._test_ll(llvmIr)

    def test_speculatePredecessor0(self):
        # note: based on HlsPythonHwrange_fromInt2
        llvmIr = """\
        define void @test_speculatePredecessor0(ptr addrspace(1) %o) {
        bb0:
          br label %bb.loop1.head

        bb.loop1.head:                                    ; preds = %bb0, %bb.loop0.latch
          %i0 = phi i3 [ %2, %bb.loop0.latch ], [ 0, %bb0 ]
          %i1 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i0, i3 0) #2
          br label %bb.loop2.head
        
        bb.loop2.head:                                    ; preds = %bb.loop2.head, %bb.loop1.head
          %i2 = phi i3 [ 0, %bb.loop1.head ], [ %1, %bb.loop2.head ]
          %i3 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i2, i3 0) #2
          %0 = call i8 @hwtHls.bitConcat.i2.i2.i4(i2 %i3, i2 %i1, i4 0) #2
          store volatile i8 %0, ptr addrspace(1) %o, align 1
          %1 = add i3 %i2, 1
          %hwrange.continue4.not = icmp eq i3 %1, -4
          %2 = add i3 %i0, 1
          %hwrange.continue.not.le.le = icmp eq i3 %2, -4
          br i1 %hwrange.continue4.not, label %bb.loop0.latch, label %bb.loop2.head
        
        bb.loop0.latch:                                   ; preds = %bb.loop2.head
          br label %bb.loop1.head
        }
        """
        self._test_ll(llvmIr)

    def test_speculatePredecessor1(self):
        # :note: based on HlsPythonHwrange_fromInt2
        # :note: test_speculatePredecessor0 in 1 additional loop
        llvmIr = """\
        define void @test_speculatePredecessor1(ptr addrspace(1) %o) {
        bb0:
          br label %bb.loop0.head
        
        bb.loop0.head:                                    ; preds = %bb.loop0.latch, %bb0
          br label %bb.loop1.head
        
        bb.loop1.head:                              ; preds = %bb.loop0.head, %bb.loop0.latch
          %i0 = phi i3 [ 0, %bb.loop0.head ], [ %2, %bb.loop0.latch ]
          %i1 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i0, i3 0) #2
          br label %bb.loop2.head
        
        bb.loop2.head:                        ; preds = %bb.loop2.head, %bb.loop1.head
          %i2 = phi i3 [ 0, %bb.loop1.head ], [ %1, %bb.loop2.head ]
          %i3 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i2, i3 0) #2
          %0 = call i8 @hwtHls.bitConcat.i2.i2.i4(i2 %i3, i2 %i1, i4 0) #2
          store volatile i8 %0, ptr addrspace(1) %o, align 1
          %1 = add i3 %i2, 1
          %hwrange.continue4.not = icmp eq i3 %1, -4
          %2 = add i3 %i0, 1
          %hwrange.continue.not.le.le = icmp eq i3 %2, -4
          br i1 %hwrange.continue4.not, label %bb.loop0.latch, label %bb.loop2.head
        
        bb.loop0.latch:                        ; preds = %bb.loop2.head
          br i1 %hwrange.continue.not.le.le, label %bb.loop0.head, label %bb.loop1.head
        }
        """
        self._test_ll(llvmIr)

    def test_speculatePredecessor2(self):
        # :note: based on HlsPythonHwrange_fromInt1_breakBefore
        llvmIr = """\
        define void @HlsPythonHwrange_fromInt1_breakBefore.mainThread(ptr addrspace(1) %o) {
        bb0:
          br label %bb.loop0.head
        
        bb.loop0.head:                              ; preds = %bb.loop0.latch, %bb0
          %i0 = phi i4 [ 0, %bb0 ], [ %i0.be, %bb.loop0.latch ]
          %0 = icmp eq i4 %i0, 4
          %1 = zext i4 %i0 to i8
          br i1 %0, label %bb2, label %bb1
        
        bb1:                              ; preds = %bb.loop0.head
          store volatile i8 %1, ptr addrspace(1) %o, align 1
          %2 = add nuw i4 %i0, 1
          %hwrange.continue = icmp ne i4 %2, -8
          br i1 %hwrange.continue, label %bb.loop0.latch, label %bb2
        
        bb2:                                   ; preds = %bb.loop0.head, %bb1
          br label %bb.loop0.latch
          
        bb.loop0.latch:                     ; preds = %bb1, %bb2
          %i0.be = phi i4 [ 0, %bb2 ], [ %2, %bb1 ]
          br label %bb.loop0.head
        }
        """
        self._test_ll(llvmIr)

    def test_tryHoistFromCheapBlocksWithSwitchLikeCmpBr0(self):
        # :note: the result should not change because bb.c0 is loop heaer
        llvmIr = """\
        define void @test_tryHoistFromCheapBlocksWithSwitchLikeCmpBr0(ptr addrspace(1) %o) {
        bb0:
          br label %bb.c0
        
        bb.c0:                                            ; preds = %bb.exit, %bb0
          %i = phi i4 [ 0, %bb0 ], [ %i.be, %bb.exit ]
          %0 = icmp eq i4 %i, 4
          %1 = zext i4 %i to i8
          br i1 %0, label %bb.def, label %bb.c1
        
        bb.c1:                                            ; preds = %bb.c0
          store volatile i8 %1, ptr addrspace(1) %o, align 1
          %2 = add nuw i4 %i, 1
          %hwrange.continue10.not = icmp eq i4 %i, 7
          br i1 %hwrange.continue10.not, label %bb.def, label %bb.exit
        
        bb.exit:                                          ; preds = %bb.def, %bb.c1
          %i.be = phi i4 [ 0, %bb.def ], [ %2, %bb.c1 ]
          br label %bb.c0
        
        bb.def:                                           ; preds = %bb.c1, %bb.c0
          br label %bb.exit
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_TC)
    # suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_TC('test_noSuboptimalLoopUnswitch')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
