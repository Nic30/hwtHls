define void @test_streamWriteMerge_implicationAssumes2(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %loop.pkt.eof, %bb0
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %loop.pkt.read

loop.pkt.read:                                    ; preds = %loop.pkt.lastCheck.3.writesExit, %loop.pkt
  %curLen.013 = phi i9 [ 0, %loop.pkt ], [ %28, %loop.pkt.lastCheck.3.writesExit ]
  %.w0 = load volatile i37, ptr addrspace(1) %rx, align 8
  %0 = call i3 @hwtHls.bitRangeGet.i37.i7.i3.33(i37 %.w0, i7 33) #5
  %1 = call i2 @hwtHls.bitRangeGet.i37.i7.i2.33(i37 %.w0, i7 33) #5
  %2 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.16(i37 %.w0, i7 16) #5
  %3 = call i8 @hwtHls.bitRangeGet.i37.i7.i8.24(i37 %.w0, i7 24) #5
  %4 = call i16 @hwtHls.bitRangeGet.i37.i7.i16.0(i37 %.w0, i7 0) #5
  %5 = call i2 @hwtHls.bitRangeGet.i37.i7.i2.35(i37 %.w0, i7 35) #5
  %6 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %.w0, i7 35) #5
  %7 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.34(i37 %.w0, i7 34) #5
  %8 = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %.w0, i7 32) #5
  %9 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %.w0, i7 32) #5
  %10 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.w0, i7 36) #5
  %11 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.w0, i7 33) #5
  %prevMaskBit1Impl46 = icmp ule i1 %11, %9
  call void @llvm.assume(i1 %prevMaskBit1Impl46)
  %maskBitNonLastImpl47 = or i1 %10, %11
  call void @llvm.assume(i1 %maskBitNonLastImpl47)
  %prevMaskBit1Impl48 = icmp ule i1 %7, %11
  call void @llvm.assume(i1 %prevMaskBit1Impl48)
  %maskBitNonLastImpl49 = or i1 %10, %7
  call void @llvm.assume(i1 %maskBitNonLastImpl49)
  %prevMaskBit1Impl50 = icmp ule i1 %6, %7
  call void @llvm.assume(i1 %prevMaskBit1Impl50)
  %maskBitNonLastImpl51 = icmp ne i2 %5, 0
  call void @llvm.assume(i1 %maskBitNonLastImpl51)
  %12 = icmp eq i4 %8, -1
  %maskAll1ifLastImpl52 = or i1 %10, %12
  call void @llvm.assume(i1 %maskAll1ifLastImpl52)
  %13 = xor i1 %11, true
  %14 = and i1 %10, %13
  %15 = icmp ult i9 %curLen.013, 128
  %wEn3 = and i1 %9, %15
  %16 = icmp eq i9 %curLen.013, 127
  %17 = or i1 %14, %16
  %.023 = and i1 %wEn3, %17
  %18 = xor i1 %7, true
  %19 = and i1 %10, %18
  %20 = xor i4 %8, -1
  %21 = call i4 @llvm.cttz.i4(i4 %20, i1 false)
  %22 = zext i4 %21 to i10
  %23 = zext i9 %curLen.013 to i10
  %24 = add nuw i10 %23, %22
  %25 = xor i1 %6, true
  %26 = and i1 %10, %25
  %27 = call i10 @llvm.umin.i10(i10 %24, i10 128)
  %28 = trunc i10 %27 to i9
  %29 = icmp eq i10 %24, 127
  %30 = or i1 %19, %29
  %31 = icmp ult i10 %24, 128
  %wEn3.1 = and i1 %11, %31
  %.025 = and i1 %wEn3.1, %30
  %32 = or i1 %26, %29
  %wEn3.2 = and i1 %7, %31
  %.031 = and i1 %wEn3.2, %32
  %33 = or i1 %10, %29
  %wEn3.3 = and i1 %6, %31
  %.037 = and i1 %wEn3.3, %33
  %34 = xor i1 %14, true
  %35 = icmp ne i2 %1, -1
  %36 = and i1 %10, %35
  %37 = xor i1 %36, true
  %38 = icmp ne i3 %0, -1
  %39 = and i1 %10, %38
  %40 = xor i1 %39, true
  %.streamWrite.en21.2 = and i1 %40, %wEn3.3
  %.239 = and i1 %40, %.037
  %.streamWrite.en19.2 = and i1 %37, %wEn3.2
  %.233 = and i1 %37, %.031
  %.227 = and i1 %34, %.025
  %41 = or i1 %wEn3, %wEn3.1
  %42 = call i2 @hwtHls.bitConcat.i1.i1(i1 %wEn3, i1 %wEn3.1) #5
  %43 = or i1 %.023, %.227
  br i1 %41, label %loop.pkt.write.1, label %loop.pkt.write.2.guard

loop.pkt.write.1:                                 ; preds = %loop.pkt.read
  call void @hwtHls.streamWrite.masked.p2.i16.i2.i1(ptr addrspace(2) %tx, i16 %4, i2 %42, i1 %43) #4
  br label %loop.pkt.write.2.guard

loop.pkt.write.2.guard:                           ; preds = %loop.pkt.write.1, %loop.pkt.read
  br i1 %.streamWrite.en19.2, label %loop.pkt.write.2, label %loop.pkt.write.3.guard

loop.pkt.write.2:                                 ; preds = %loop.pkt.write.2.guard
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %2, i1 %.233) #4
  br label %loop.pkt.write.3.guard

loop.pkt.write.3.guard:                           ; preds = %loop.pkt.write.2, %loop.pkt.write.2.guard
  %impCache = icmp ule i1 %wEn3.1, %wEn3
  br i1 %.streamWrite.en21.2, label %loop.pkt.write.3, label %loop.pkt.lastCheck.3.writesExit

loop.pkt.write.3:                                 ; preds = %loop.pkt.write.3.guard
  call void @llvm.assume(i1 %impCache)
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %3, i1 %.239) #4
  br label %loop.pkt.lastCheck.3.writesExit

loop.pkt.lastCheck.3.writesExit:                  ; preds = %loop.pkt.write.3, %loop.pkt.write.3.guard
  br i1 %10, label %loop.pkt.eof, label %loop.pkt.read

loop.pkt.eof:                                     ; preds = %loop.pkt.lastCheck.3.writesExit
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %loop.pkt
}
