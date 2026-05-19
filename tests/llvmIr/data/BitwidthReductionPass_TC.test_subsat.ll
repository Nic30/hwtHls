define void @test_subsat(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %acc0 = load volatile i4, ptr addrspace(1) %data_in, align 4
  %div0 = load volatile i4, ptr addrspace(1) %data_in, align 4
  %lsbShIn = load volatile i1, ptr addrspace(1) %data_in, align 4
  %subLhs = call i5 @hwtHls.bitConcat.i1.i4(i1 %lsbShIn, i4 %acc0) #1
  %0 = call i5 @hwtHls.bitConcat.i1.i4(i1 %lsbShIn, i4 %acc0) #1
  %1 = zext i4 %div0 to i5
  %2 = icmp uge i5 %0, %1
  %subRhs1 = select i1 %2, i4 %div0, i4 0
  %3 = zext i4 %subRhs1 to i5
  %accNext = sub i5 %subLhs, %3
  store volatile i5 %accNext, ptr addrspace(2) %data_out, align 4
  br label %bb1
}
