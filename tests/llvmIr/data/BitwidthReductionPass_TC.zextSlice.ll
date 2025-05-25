define void @zextSlice(ptr addrspace(1) %i0, ptr addrspace(2) %o0) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb0
  %0 = load volatile i16, ptr addrspace(1) %i0, align 1
  %1 = zext i16 %0 to i32
  store volatile i32 %1, ptr addrspace(2) %o0, align 4
  ret void
}
