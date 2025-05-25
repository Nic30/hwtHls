define void @selectOfShiftedSameRegSlices(ptr addrspace(1) %i0, ptr addrspace(1) %i1, ptr addrspace(2) %o0) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb0
  %c = load volatile i1, ptr addrspace(1) %i0, align 1
  %d = load volatile i24, ptr addrspace(1) %i1, align 4
  %d_16_8 = call i8 @hwtHls.bitRangeGet.i24.i6.i8.8(i24 %d, i6 8) #1
  %d_16_0 = call i16 @hwtHls.bitRangeGet.i24.i6.i16.0(i24 %d, i6 0) #1
  %0 = zext i8 %d_16_8 to i16
  %res1 = select i1 %c, i16 %d_16_0, i16 %0
  %1 = zext i16 %res1 to i24
  store volatile i24 %1, ptr addrspace(2) %o0, align 4
  ret void
}
