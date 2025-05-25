define void @streamWriteMerge_implicationAssumes0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %loop.pkt.lastCheck, %bb0
  br label %loop.pkt.read

loop.pkt.read:                                    ; preds = %loop.pkt.lastCheck, %loop.pkt
  %curLen.0 = phi i9 [ 0, %loop.pkt ], [ %20, %loop.pkt.lastCheck ]
  %.w0 = load volatile i37, ptr addrspace(1) %rx, align 8
  %0 = call i3 @hwtHls.bitRangeGet.i37.i7.i3.33(i37 %.w0, i7 33) #4
  %1 = call i2 @hwtHls.bitRangeGet.i37.i7.i2.33(i37 %.w0, i7 33) #4
  %2 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %.w0, i7 35) #4
  %3 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.34(i37 %.w0, i7 34) #4
  %4 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %.w0, i7 32) #4
  %5 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.w0, i7 33) #4
  %6 = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %.w0, i7 32) #4
  %data.3.0 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.24(i37 %.w0, i7 24) #4
  %7 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.16(i37 %.w0, i7 16) #4
  %8 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.8(i37 %.w0, i7 8) #4
  %rx.last = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.w0, i7 36) #4
  %data.0 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.0(i37 %.w0, i7 0) #4
  %prevMaskBit1Impl = icmp ule i1 %5, %4
  call void @llvm.assume(i1 %prevMaskBit1Impl)
  %prevMaskBit1Impl42 = icmp ule i1 %3, %5
  call void @llvm.assume(i1 %prevMaskBit1Impl42)
  %prevMaskBit1Impl43 = icmp ule i1 %2, %3
  call void @llvm.assume(i1 %prevMaskBit1Impl43)
  %9 = xor i1 %5, true
  %10 = and i1 %rx.last, %9
  %11 = icmp eq i9 %curLen.0, 127
  %12 = or i1 %10, %11
  %eof.0 = and i1 %4, %12
  %13 = xor i1 %3, true
  %14 = and i1 %rx.last, %13
  %15 = xor i1 %2, true
  %16 = and i1 %rx.last, %15
  %17 = xor i4 %6, -1
  %18 = call i4 @llvm.cttz.i4(i4 %17, i1 false)
  %19 = zext i4 %18 to i9
  %curLen.1 = add i9 %curLen.0, %19
  %20 = call i9 @llvm.umin.i9(i9 %curLen.1, i9 127)
  %21 = icmp eq i9 %curLen.1, 127
  %22 = or i1 %14, %21
  %23 = icmp ne i9 %curLen.1, 128
  %writeEn3.1 = and i1 %5, %23
  %.025 = and i1 %writeEn3.1, %22
  %24 = or i1 %16, %21
  %writeEn3.2 = and i1 %3, %23
  %.031 = and i1 %writeEn3.2, %24
  %25 = or i1 %rx.last, %21
  %writeEn3.3 = and i1 %2, %23
  %.037 = and i1 %writeEn3.3, %25
  %26 = xor i1 %10, true
  %27 = icmp ne i2 %1, -1
  %28 = and i1 %rx.last, %27
  %29 = xor i1 %28, true
  %30 = icmp ne i3 %0, -1
  %31 = and i1 %rx.last, %30
  %32 = xor i1 %31, true
  %.streamWrite.en21.2 = and i1 %32, %writeEn3.3
  %eof.3 = and i1 %32, %.037
  %data.3 = select i1 %31, i8 undef, i8 %data.3.0
  %.streamWrite.en19.2 = and i1 %29, %writeEn3.2
  %eof.2 = and i1 %29, %.031
  %.230 = select i1 %28, i8 undef, i8 %7
  %eof.1 = and i1 %26, %.025
  %data.1 = select i1 %10, i8 undef, i8 %8
  %impCache = icmp ule i1 %writeEn3.1, %4
  call void @llvm.assume(i1 %impCache)
  %impCache1 = icmp ule i1 %.streamWrite.en19.2, %writeEn3.1
  call void @llvm.assume(i1 %impCache1)
  %33 = call i24 @hwtHls.bitConcat.i8.i8.i8(i8 %data.0, i8 %data.1, i8 %.230) #4
  %34 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %4, i1 %writeEn3.1, i1 %.streamWrite.en19.2) #4
  %35 = or i1 %eof.0, %eof.1
  %36 = or i1 %35, %eof.2
  %37 = select i1 %4, i3 %34, i3 0
  br i1 %4, label %bb.w2, label %bb.w3.guard

bb.w2:                                            ; preds = %loop.pkt.read
  call void @hwtHls.streamWrite.masked.p2.i24.i3.i1(ptr addrspace(2) %tx, i24 %33, i3 %34, i1 %36) #5
  br label %bb.w3.guard

bb.w3.guard:                                      ; preds = %bb.w2, %loop.pkt.read
  br i1 %.streamWrite.en21.2, label %bb.w3, label %loop.pkt.lastCheck

bb.w3:                                            ; preds = %bb.w3.guard
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %data.3, i1 %eof.3) #5
  br label %loop.pkt.lastCheck

loop.pkt.lastCheck:                               ; preds = %bb.w3, %bb.w3.guard
  br i1 %rx.last, label %loop.pkt, label %loop.pkt.read
}
