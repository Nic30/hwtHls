define void @selectOfPartlySameRegSlices(ptr addrspace(1) %i0, ptr addrspace(1) %i1, ptr addrspace(2) %o0) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb0
  %c = load volatile i1, ptr addrspace(1) %i0, align 1
  %d = load volatile i24, ptr addrspace(1) %i1, align 4
  %0 = call i8 @hwtHls.bitRangeGet.i24.i6.i8.8(i24 %d, i6 8) #1
  %d_8_0 = call i8 @hwtHls.bitRangeGet.i24.i6.i8.0(i24 %d, i6 0) #1
  %res1 = select i1 %c, i8 %0, i8 0
  %1 = call i24 @hwtHls.bitConcat.i8.i8.i8(i8 %d_8_0, i8 %res1, i8 0) #1
  store volatile i24 %1, ptr addrspace(2) %o0, align 4
  ret void
}
