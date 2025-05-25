define void @selectValOrUndef(ptr addrspace(1) %i0, ptr addrspace(1) %i1, ptr addrspace(2) %o0) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb0
  %c = load volatile i1, ptr addrspace(1) %i0, align 1
  %d = load volatile i8, ptr addrspace(1) %i1, align 4
  store volatile i8 %d, ptr addrspace(2) %o0, align 1
  ret void
}
