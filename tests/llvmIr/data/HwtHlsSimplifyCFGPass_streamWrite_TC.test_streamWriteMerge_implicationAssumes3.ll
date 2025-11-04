define void @test_streamWriteMerge_implicationAssumes3(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !hwtHls.io !0 {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %loop.pkt.eof, %bb0
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %loop.pkt.read

loop.pkt.read:                                    ; preds = %loop.pkt.lastCheck.2.writesExit, %loop.pkt
  %curLen.013 = phi i9 [ 0, %loop.pkt ], [ %25, %loop.pkt.lastCheck.2.writesExit ]
  %.w0 = load volatile i28, ptr addrspace(1) %rx, align 4
  %0 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.25(i28 %.w0, i6 25) #5
  %1 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.16(i28 %.w0, i6 16) #5
  %2 = call i16 @hwtHls.bitRangeGet.i28.i6.i16.0(i28 %.w0, i6 0) #5
  %3 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.24(i28 %.w0, i6 24) #5
  %4 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.26(i28 %.w0, i6 26) #5
  %5 = call i3 @hwtHls.bitRangeGet.i28.i6.i3.24(i28 %.w0, i6 24) #5
  %6 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.24(i28 %.w0, i6 24) #5
  %7 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %.w0, i6 27) #5
  %8 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.25(i28 %.w0, i6 25) #5
  %prevMaskBit1Impl35 = icmp ule i1 %8, %6
  call void @llvm.assume(i1 %prevMaskBit1Impl35)
  %maskBitNonLastImpl36 = or i1 %7, %8
  call void @llvm.assume(i1 %maskBitNonLastImpl36)
  %prevMaskBit1Impl37 = icmp ule i1 %4, %8
  call void @llvm.assume(i1 %prevMaskBit1Impl37)
  %9 = icmp eq i2 %3, -1
  %prevMaskBitAll1Impl38 = icmp ule i1 %4, %9
  call void @llvm.assume(i1 %prevMaskBitAll1Impl38)
  %10 = or i1 %7, %4
  call void @llvm.assume(i1 %10)
  %11 = icmp eq i3 %5, -1
  %maskAll1ifLastImpl40 = or i1 %7, %11
  call void @llvm.assume(i1 %maskAll1ifLastImpl40)
  %12 = xor i1 %8, true
  %13 = and i1 %7, %12
  %14 = icmp ult i9 %curLen.013, 128
  %wEn3 = and i1 %6, %14
  %15 = icmp eq i9 %curLen.013, 127
  %16 = or i1 %13, %15
  %.021 = and i1 %wEn3, %16
  %17 = xor i1 %4, true
  %18 = and i1 %7, %17
  %19 = xor i3 %5, -1
  %20 = call i3 @llvm.cttz.i3(i3 %19, i1 false)
  %21 = zext i3 %20 to i10
  %22 = zext i9 %curLen.013 to i10
  %23 = add nuw i10 %22, %21
  %24 = call i10 @llvm.umin.i10(i10 %23, i10 128)
  %25 = trunc i10 %24 to i9
  %26 = icmp eq i10 %23, 127
  %27 = or i1 %18, %26
  %28 = icmp ult i10 %23, 128
  %wEn3.1 = and i1 %8, %28
  %.023 = and i1 %wEn3.1, %27
  %29 = or i1 %7, %26
  %wEn3.2 = and i1 %4, %28
  %.029 = and i1 %wEn3.2, %29
  %30 = icmp ne i2 %0, -1
  %31 = and i1 %7, %30
  %32 = xor i1 %31, true
  %.streamWrite.en19.2 = and i1 %32, %wEn3.2
  %.231 = and i1 %32, %.029
  %33 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %wEn3.1) #5
  %34 = or i1 %.021, %.023
  br i1 %wEn3, label %loop.pkt.write.1.streamWrite.sinked, label %35

loop.pkt.write.1.streamWrite.sinked:              ; preds = %loop.pkt.read
  call void @hwtHls.streamWrite.masked.p2.i16.i2.i1.i1.p0(ptr addrspace(2) %tx, i16 %2, i2 %33, i1 false, i1 %34, ptr null) #4
  br label %35

35:                                               ; preds = %loop.pkt.write.1.streamWrite.sinked, %loop.pkt.read
  %impCache = icmp ule i1 %wEn3.1, %wEn3
  br i1 %.streamWrite.en19.2, label %loop.pkt.write.2.streamWrite.sinked, label %loop.pkt.lastCheck.2.writesExit

loop.pkt.write.2.streamWrite.sinked:              ; preds = %35
  call void @llvm.assume(i1 %impCache)
  call void @hwtHls.streamWrite.p2.i8.i1.i1.p0(ptr addrspace(2) %tx, i8 %1, i1 false, i1 %.231, ptr null) #4
  br label %loop.pkt.lastCheck.2.writesExit

loop.pkt.lastCheck.2.writesExit:                  ; preds = %loop.pkt.write.2.streamWrite.sinked, %35
  br i1 %7, label %loop.pkt.eof, label %loop.pkt.read

loop.pkt.eof:                                     ; preds = %loop.pkt.lastCheck.2.writesExit
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %loop.pkt
}
