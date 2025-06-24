define void @streamWriteMerge_implicationAssumes1(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %loop.pkt.lastCheck.6.writesExit, %bb0
  br label %loop.pkt.read

loop.pkt.read:                                    ; preds = %loop.pkt.lastCheck.6.writesExit, %loop.pkt
  %curLen.013 = phi i9 [ 0, %loop.pkt ], [ %38, %loop.pkt.lastCheck.6.writesExit ]
  %.w0 = load volatile i64, ptr addrspace(1) %rx, align 8
  %0 = call i6 @hwtHls.bitRangeGet.i64.i7.i6.57(i64 %.w0, i7 57) #4
  %1 = call i5 @hwtHls.bitRangeGet.i64.i7.i5.57(i64 %.w0, i7 57) #4
  %2 = call i4 @hwtHls.bitRangeGet.i64.i7.i4.57(i64 %.w0, i7 57) #4
  %3 = call i3 @hwtHls.bitRangeGet.i64.i7.i3.57(i64 %.w0, i7 57) #4
  %4 = call i2 @hwtHls.bitRangeGet.i64.i7.i2.57(i64 %.w0, i7 57) #4
  %5 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.57(i64 %.w0, i7 57) #4
  %6 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.56(i64 %.w0, i7 56) #4
  %7 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.58(i64 %.w0, i7 58) #4
  %8 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.59(i64 %.w0, i7 59) #4
  %9 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.60(i64 %.w0, i7 60) #4
  %10 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.61(i64 %.w0, i7 61) #4
  %11 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.62(i64 %.w0, i7 62) #4
  %12 = call i1 @hwtHls.bitRangeGet.i64.i7.i1.63(i64 %.w0, i7 63) #4
  %13 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.0(i64 %.w0, i7 0) #4
  %14 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.8(i64 %.w0, i7 8) #4
  %15 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.16(i64 %.w0, i7 16) #4
  %16 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.24(i64 %.w0, i7 24) #4
  %17 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.32(i64 %.w0, i7 32) #4
  %18 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.40(i64 %.w0, i7 40) #4
  %19 = call i8 @hwtHls.bitRangeGet.i64.i7.i8.48(i64 %.w0, i7 48) #4
  %20 = call i7 @hwtHls.bitRangeGet.i64.i7.i7.56(i64 %.w0, i7 56) #4
  %prevMaskBit1Impl = icmp ule i1 %5, %6
  call void @llvm.assume(i1 %prevMaskBit1Impl)
  %prevMaskBit1Impl65 = icmp ule i1 %7, %5
  call void @llvm.assume(i1 %prevMaskBit1Impl65)
  %prevMaskBit1Impl66 = icmp ule i1 %8, %7
  call void @llvm.assume(i1 %prevMaskBit1Impl66)
  %prevMaskBit1Impl67 = icmp ule i1 %9, %8
  call void @llvm.assume(i1 %prevMaskBit1Impl67)
  %prevMaskBit1Impl68 = icmp ule i1 %10, %9
  call void @llvm.assume(i1 %prevMaskBit1Impl68)
  %prevMaskBit1Impl69 = icmp ule i1 %11, %10
  call void @llvm.assume(i1 %prevMaskBit1Impl69)
  %21 = xor i1 %5, true
  %22 = and i1 %12, %21
  %23 = icmp eq i9 %curLen.013, 127
  %24 = or i1 %22, %23
  %.029 = and i1 %6, %24
  %25 = xor i1 %7, true
  %26 = and i1 %12, %25
  %27 = xor i1 %8, true
  %28 = and i1 %12, %27
  %29 = xor i1 %9, true
  %30 = and i1 %12, %29
  %31 = xor i1 %10, true
  %32 = and i1 %12, %31
  %33 = xor i1 %11, true
  %34 = and i1 %12, %33
  %35 = xor i7 %20, -1
  %36 = call i7 @llvm.cttz.i7(i7 %35, i1 false)
  %37 = zext i7 %36 to i9
  %curLen.114.6 = add i9 %curLen.013, %37
  %38 = call i9 @llvm.umin.i9(i9 %curLen.114.6, i9 127)
  %39 = icmp eq i9 %curLen.114.6, 127
  %40 = or i1 %26, %39
  %41 = icmp ne i9 %curLen.114.6, 128
  %writeEn3.1 = and i1 %5, %41
  %.031 = and i1 %writeEn3.1, %40
  %42 = or i1 %28, %39
  %writeEn3.2 = and i1 %7, %41
  %.037 = and i1 %writeEn3.2, %42
  %43 = or i1 %30, %39
  %writeEn3.3 = and i1 %8, %41
  %.043 = and i1 %writeEn3.3, %43
  %44 = or i1 %32, %39
  %writeEn3.4 = and i1 %9, %41
  %.049 = and i1 %writeEn3.4, %44
  %45 = or i1 %34, %39
  %writeEn3.5 = and i1 %10, %41
  %.055 = and i1 %writeEn3.5, %45
  %46 = or i1 %12, %39
  %writeEn3.6 = and i1 %11, %41
  %.061 = and i1 %writeEn3.6, %46
  %47 = xor i1 %22, true
  %48 = icmp ne i2 %4, -1
  %49 = and i1 %12, %48
  %50 = xor i1 %49, true
  %51 = icmp ne i3 %3, -1
  %52 = and i1 %12, %51
  %53 = xor i1 %52, true
  %54 = icmp ne i4 %2, -1
  %55 = and i1 %12, %54
  %56 = xor i1 %55, true
  %57 = icmp ne i5 %1, -1
  %58 = and i1 %12, %57
  %59 = xor i1 %58, true
  %60 = icmp ne i6 %0, -1
  %61 = and i1 %12, %60
  %62 = xor i1 %61, true
  %.streamWrite.en27.2 = and i1 %62, %writeEn3.6
  %.263 = and i1 %62, %.061
  %.260 = select i1 %61, i8 undef, i8 %19
  %.streamWrite.en25.2 = and i1 %59, %writeEn3.5
  %.257 = and i1 %59, %.055
  %.254 = select i1 %58, i8 undef, i8 %18
  %.streamWrite.en23.2 = and i1 %56, %writeEn3.4
  %.251 = and i1 %56, %.049
  %.248 = select i1 %55, i8 undef, i8 %17
  %.streamWrite.en21.2 = and i1 %53, %writeEn3.3
  %.245 = and i1 %53, %.043
  %.242 = select i1 %52, i8 undef, i8 %16
  %.streamWrite.en19.2 = and i1 %50, %writeEn3.2
  %.239 = and i1 %50, %.037
  %.236 = select i1 %49, i8 undef, i8 %15
  %.233 = and i1 %47, %.031
  %.2 = select i1 %22, i8 undef, i8 %14
  %63 = or i1 %6, %writeEn3.1
  %64 = or i1 %63, %.streamWrite.en19.2
  %65 = or i1 %64, %.streamWrite.en21.2
  %66 = or i1 %65, %.streamWrite.en23.2
  %67 = or i1 %66, %.streamWrite.en25.2
  %68 = call i48 @hwtHls.bitConcat.i8.i8.i8.i8.i8.i8(i8 %13, i8 %.2, i8 %.236, i8 %.242, i8 %.248, i8 %.254) #4
  %69 = call i6 @hwtHls.bitConcat.i1.i1.i1.i1.i1.i1(i1 %6, i1 %writeEn3.1, i1 %.streamWrite.en19.2, i1 %.streamWrite.en21.2, i1 %.streamWrite.en23.2, i1 %.streamWrite.en25.2) #4
  %70 = or i1 %.029, %.233
  %71 = or i1 %70, %.239
  %72 = or i1 %71, %.245
  %73 = or i1 %72, %.251
  %74 = or i1 %73, %.257
  %75 = select i1 %67, i6 %69, i6 0
  br i1 %67, label %loop.pkt.write.5.streamWrite.sinked, label %76

loop.pkt.write.5.streamWrite.sinked:              ; preds = %loop.pkt.read
  call void @hwtHls.streamWrite.masked.p2.i48.i6.i1(ptr addrspace(2) %tx, i48 %68, i6 %69, i1 %74) #5
  br label %76

76:                                               ; preds = %loop.pkt.write.5.streamWrite.sinked, %loop.pkt.read
  br i1 %.streamWrite.en27.2, label %loop.pkt.write.6.streamWrite.sinked, label %loop.pkt.lastCheck.6.writesExit

loop.pkt.write.6.streamWrite.sinked:              ; preds = %76
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %.260, i1 %.263) #5
  br label %loop.pkt.lastCheck.6.writesExit

loop.pkt.lastCheck.6.writesExit:                  ; preds = %loop.pkt.write.6.streamWrite.sinked, %76
  br i1 %12, label %loop.pkt, label %loop.pkt.read
}
