define void @BitwidthReductionPass_PHI_TC.test_phiRmRight1.ll(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %data_in_read1 = load volatile i18, ptr addrspace(1) %data_in, align 4
  %0 = trunc i18 %data_in_read1 to i1
  %1 = sext i1 %0 to i9
  %conc = xor i9 %1, -1
  %2 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.7(i9 %conc, i5 7) #1
  %3 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.6(i9 %conc, i5 6) #1
  %4 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.5(i9 %conc, i5 5) #1
  %5 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.4(i9 %conc, i5 4) #1
  %6 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.3(i9 %conc, i5 3) #1
  %7 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.2(i9 %conc, i5 2) #1
  %8 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.1(i9 %conc, i5 1) #1
  %9 = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %conc, i5 8) #1
  %10 = trunc i9 %conc to i1
  %11 = call i8 @hwtHls.bitConcat.i1.i1.i1.i1.i1.i1.i1.i1(i1 %10, i1 %8, i1 %7, i1 %6, i1 %5, i1 %4, i1 %3, i1 %2) #1
  %12 = zext i1 %9 to i9
  call void @hwtHls.pyObjectPlaceholder.0.HwSimCallback.i44(i32 0, i9 %12)
  %13 = call i9 @hwtHls.bitConcat.i1.i8(i1 %10, i8 %11) #1
  call void @hwtHls.pyObjectPlaceholder.0.HwSimCallback.i44(i32 0, i9 %13)
  br label %bb1
}
