define void @test_cttz_withIntermediateUse(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %loop.pkt.eof, %bb0
  br label %loop.pkt.read

loop.pkt.read:                                    ; preds = %bb.w.exit, %loop.pkt
  %curLen.0.in = phi i2 [ 0, %loop.pkt ], [ %13, %bb.w.exit ]
  %0 = load volatile i4, ptr addrspace(1) %rx, align 1
  %1 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.1(i4 %0, i3 1) #3
  %strb = call i3 @hwtHls.bitRangeGet.i4.i3.i3.0(i4 %0, i3 0) #3
  %strb0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %0, i3 0) #3
  %strb1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %0, i3 1) #3
  %strb2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.2(i4 %0, i3 2) #3
  %last = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %0, i3 3) #3
  %prevMaskBit1Impl = icmp ule i1 %strb1, %strb0
  call void @llvm.assume(i1 %prevMaskBit1Impl)
  %maskBitNonLastImpl = or i1 %last, %strb1
  call void @llvm.assume(i1 %maskBitNonLastImpl)
  %prevMaskBit1Impl33 = icmp ule i1 %strb2, %strb1
  call void @llvm.assume(i1 %prevMaskBit1Impl33)
  %2 = or i1 %last, %strb2
  call void @llvm.assume(i1 %2)
  %3 = icmp eq i3 %strb, -1
  %maskAll1ifLastImpl = or i1 %last, %3
  call void @llvm.assume(i1 %maskAll1ifLastImpl)
  %limit.0 = icmp ult i2 %curLen.0.in, 1
  %wEn.0 = and i1 %strb0, %limit.0
  %4 = xor i3 %strb, -1
  %5 = call i3 @llvm.cttz.i3(i3 %4, i1 false)
  %6 = call i3 @llvm.umin.i3(i3 %5, i3 2)
  %7 = call i3 @llvm.umin.i3(i3 %5, i3 1)
  %8 = zext i2 %curLen.0.in to i3
  %9 = add i3 %8, %7
  %10 = add i3 %8, %6
  %11 = add i3 %8, %5
  %12 = call i3 @llvm.umin.i3(i3 %11, i3 1)
  %13 = trunc i3 %12 to i2
  %limit.1 = icmp ult i3 %9, 1
  %wEn.1 = and i1 %strb1, %limit.1
  %limit.2 = icmp ult i3 %10, 1
  %wEn.0.2 = and i1 %strb2, %limit.2
  %14 = icmp ne i2 %1, -1
  %15 = and i1 %last, %14
  %16 = xor i1 %15, true
  %wEn.2 = and i1 %16, %wEn.0.2
  %17 = or i1 %wEn.0, %wEn.1
  %wEn.any = or i1 %17, %wEn.2
  %18 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %wEn.0, i1 %wEn.1, i1 %wEn.2) #3
  br i1 %wEn.any, label %bb.w, label %bb.w.exit

bb.w:                                             ; preds = %loop.pkt.read
  store volatile i3 %18, ptr addrspace(2) %tx, align 2
  br label %bb.w.exit

bb.w.exit:                                        ; preds = %bb.w, %loop.pkt.read
  br i1 %last, label %loop.pkt.eof, label %loop.pkt.read

loop.pkt.eof:                                     ; preds = %bb.w.exit
  br label %loop.pkt
}
