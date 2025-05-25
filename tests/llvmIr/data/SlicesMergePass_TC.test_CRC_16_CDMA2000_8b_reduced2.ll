define void @test_CRC_16_CDMA2000_8b_reduced2(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb0:
  %dataIn_read = load volatile i8, ptr addrspace(1) %dataIn, align 1
  %0 = call i6 @hwtHls.bitRangeGet.i8.i4.i6.1(i8 %dataIn_read, i4 1) #1
  %1 = call i6 @hwtHls.bitRangeGet.i8.i4.i6.0(i8 %dataIn_read, i4 0) #1
  %2 = call i3 @hwtHls.bitRangeGet.i8.i4.i3.5(i8 %dataIn_read, i4 5) #1
  %3 = call i2 @hwtHls.bitRangeGet.i8.i4.i2.6(i8 %dataIn_read, i4 6) #1
  %4 = call i3 @hwtHls.bitRangeGet.i8.i4.i3.0(i8 %dataIn_read, i4 0) #1
  %5 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8 %dataIn_read, i4 4) #1
  %6 = call i5 @hwtHls.bitRangeGet.i8.i4.i5.3(i8 %dataIn_read, i4 3) #1
  %7 = call i5 @hwtHls.bitRangeGet.i8.i4.i5.2(i8 %dataIn_read, i4 2) #1
  %8 = call i5 @hwtHls.bitRangeGet.i8.i4.i5.0(i8 %dataIn_read, i4 0) #1
  %9 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.6(i8 %dataIn_read, i4 6) #1
  %10 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.7(i8 %dataIn_read, i4 7) #1
  %11 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.5(i8 %dataIn_read, i4 5) #1
  %12 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.4(i8 %dataIn_read, i4 4) #1
  %13 = xor i6 %1, %0
  %14 = call i3 @hwtHls.bitRangeGet.i6.i4.i3.0(i6 %13, i4 0) #1
  %15 = call i1 @hwtHls.bitRangeGet.i6.i4.i1.0(i6 %13, i4 0) #1
  %16 = call i3 @hwtHls.bitRangeGet.i6.i4.i3.3(i6 %13, i4 3) #1
  %17 = xor i1 %11, %15
  %18 = xor i3 %16, %14
  %19 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %18, i3 0) #1
  %20 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %18, i3 2) #1
  %21 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %18, i3 1) #1
  %22 = xor i1 %9, %19
  %23 = call i2 @hwtHls.bitConcat.i1.i1(i1 %10, i1 %10) #1
  %24 = call i2 @hwtHls.bitConcat.i1.i1(i1 %22, i1 %21) #1
  %.opConc2 = xor i2 %23, %24
  %25 = xor i5 %8, %7
  %26 = xor i5 %6, %25
  %27 = call i4 @hwtHls.bitRangeGet.i5.i4.i4.0(i5 %26, i4 0) #1
  %28 = call i1 @hwtHls.bitRangeGet.i5.i4.i1.0(i5 %26, i4 0) #1
  %29 = call i1 @hwtHls.bitRangeGet.i5.i4.i1.4(i5 %26, i4 4) #1
  %30 = xor i4 %5, %27
  %31 = call i3 @hwtHls.bitRangeGet.i4.i3.i3.1(i4 %30, i3 1) #1
  %32 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %30, i3 0) #1
  %33 = call i2 @hwtHls.bitConcat.i1.i1(i1 %10, i1 %11) #1
  %34 = call i2 @hwtHls.bitConcat.i1.i1(i1 %17, i1 %32) #1
  %.opConc3 = xor i2 %33, %34
  %35 = xor i1 %12, %15
  %36 = xor i1 %11, %35
  %37 = call i2 @hwtHls.bitConcat.i1.i1(i1 %36, i1 %32) #1
  %.opConc1 = xor i2 %3, %37
  %38 = xor i3 %4, %2
  %39 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %38, i3 0) #1
  %40 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %38, i3 2) #1
  %41 = xor i1 %11, %19
  %42 = call i4 @hwtHls.bitConcat.i2.i2(i2 %3, i2 %3) #1
  %43 = call i4 @hwtHls.bitConcat.i1.i1.i2(i1 %41, i1 %28, i2 %39) #1
  %.opConc = xor i4 %42, %43
  %44 = call i16 @hwtHls.bitConcat.i4.i1.i2.i3.i1.i2.i1.i2(i4 %.opConc, i1 %40, i2 %.opConc1, i3 %31, i1 %29, i2 %.opConc2, i1 %20, i2 %.opConc3) #1
  store volatile i16 %44, ptr addrspace(2) %dataOut, align 2
  ret void
}
