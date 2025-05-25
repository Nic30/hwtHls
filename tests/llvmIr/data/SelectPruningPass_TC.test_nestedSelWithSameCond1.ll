define void @test_nestedSelWithSameCond1(ptr addrspace(1) %rx, ptr addrspace(2) %txBody) {
entry:
  br label %blockL44i0_L88i0_88

blockL44i0_L88i0_88:                              ; preds = %rxoff0, %entry
  %rxDataOffset.011 = phi i1 [ false, %entry ], [ %spec.select1017, %rxoff0 ]
  %rxDataLast.1 = phi i1 [ undef, %entry ], [ %rxDataLast.2, %rxoff0 ]
  %rxDataMask.112 = phi i1 [ undef, %entry ], [ %rxDataMask.214, %rxoff0 ]
  %rxData.1 = phi i16 [ undef, %entry ], [ %rxData.2, %rxoff0 ]
  %"(readEn)13" = icmp eq i1 %rxDataOffset.011, false
  br i1 %"(readEn)13", label %0, label %rxoff0

0:                                                ; preds = %blockL44i0_L88i0_88
  %"rx1(rx_read).opt" = load volatile i19, ptr addrspace(1) %rx, align 4
  %1 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %"rx1(rx_read).opt", i6 0) #1
  %2 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %"rx1(rx_read).opt", i6 18) #1
  %3 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %"rx1(rx_read).opt", i6 17) #1
  br label %rxoff0

rxoff0:                                           ; preds = %0, %blockL44i0_L88i0_88
  %rxDataLast.2 = phi i1 [ %2, %0 ], [ %rxDataLast.1, %blockL44i0_L88i0_88 ]
  %rxDataMask.214 = phi i1 [ %3, %0 ], [ %rxDataMask.112, %blockL44i0_L88i0_88 ]
  %rxData.2 = phi i16 [ %1, %0 ], [ %rxData.1, %blockL44i0_L88i0_88 ]
  %4 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %rxData.2, i5 0) #1
  %5 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %rxData.2, i5 8) #1
  %6 = xor i1 %rxDataMask.214, true
  %7 = and i1 %rxDataLast.2, %6
  %8 = xor i1 %7, true
  %9 = call i9 @hwtHls.bitConcat.i8.i1(i8 %4, i1 %7) #1
  %10 = call i9 @hwtHls.bitConcat.i8.i1(i8 %5, i1 %rxDataLast.2) #1
  %spec.select815 = select i1 %"(readEn)13", i9 %9, i9 %10
  %11 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %spec.select815, i5 8) #1
  %12 = call i8 @hwtHls.bitRangeGet.i9.i5.i8.0(i9 %spec.select815, i5 0) #1
  %spec.select916 = select i1 %"(readEn)13", i1 %8, i1 false
  store volatile i8 %12, ptr addrspace(2) %txBody, align 1
  %spec.select1017 = select i1 %11, i1 false, i1 %spec.select916
  br label %blockL44i0_L88i0_88
}
