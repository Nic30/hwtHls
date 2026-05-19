define void @test_slicesExpandingCausingSliceReoder2(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %data_in_read1 = load volatile i18, ptr addrspace(1) %data_in, align 4
  %0 = trunc i18 %data_in_read1 to i1
  %1 = trunc i18 %data_in_read1 to i7
  %2 = sext i1 %0 to i2
  %3 = call i9 @hwtHls.bitConcat.i2.i7(i2 %2, i7 %1) #1
  call void @hwtHls.pyObjectPlaceholder.0.HwSimCallback.i44(i32 0, i5 11, i9 %3)
  br label %bb1
}
