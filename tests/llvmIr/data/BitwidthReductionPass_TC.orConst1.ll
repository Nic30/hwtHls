define void @orConst1(ptr addrspace(1) %i0, ptr addrspace(2) %o0) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb0
  %0 = load volatile i8, ptr addrspace(1) %i0, align 1
  %1 = mul i8 %0, 24
  %2 = call i5 @hwtHls.bitRangeGet.i8.i4.i5.3(i8 %1, i4 3) #1
  %3 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.0(i8 %1, i4 0) #1
  %4 = call i8 @hwtHls.bitConcat.i1.i2.i5(i1 %3, i2 -1, i5 %2) #1
  store volatile i8 %4, ptr addrspace(2) %o0, align 4
  ret void
}
