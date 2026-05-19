define void @test_phiTrunc(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb4, %bb0
  %inpData_divisor.01 = phi i1 [ %8, %bb4 ], [ false, %bb0 ]
  %0 = sub nsw i16 0, 0
  %1 = call i12 @hwtHls.bitRangeGet.i16.i5.i12.0(i16 %0, i5 0) #1
  %inpData_divisor.12 = select i1 %inpData_divisor.01, i12 %1, i12 0
  br i1 false, label %bb2, label %bb4

bb2:                                              ; preds = %bb2, %bb1
  %acc.0463 = phi i12 [ 0, %bb1 ], [ %6, %bb2 ]
  %quotient.0454 = phi i1 [ false, %bb1 ], [ %3, %bb2 ]
  %2 = call i13 @hwtHls.bitConcat.i1.i12(i1 false, i12 %acc.0463) #1
  %3 = icmp ule i12 0, %acc.0463
  %4 = select i1 %3, i12 %inpData_divisor.12, i12 0
  %5 = zext i12 %4 to i13
  %accNext2236 = sub i13 %2, %5
  %6 = trunc i13 %accNext2236 to i12
  br i1 false, label %bb3, label %bb2

bb3:                                              ; preds = %bb2
  %quotient.3.le.le5 = select i1 %inpData_divisor.01, i1 %quotient.0454, i1 false
  %7 = zext i1 %quotient.3.le.le5 to i24
  store volatile i24 %7, ptr addrspace(2) %data_out, align 4
  br label %bb4

bb4:                                              ; preds = %bb3, %bb1
  %data_in_read1 = load volatile i25, ptr addrspace(1) %data_in, align 4
  %8 = call i1 @hwtHls.bitRangeGet.i25.i6.i1.0(i25 %data_in_read1, i6 0) #1
  br label %bb1
}
