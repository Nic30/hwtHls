define void @PhiChain0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %arr0 = phi i8 [ 0, %bb0 ], [ %i_read, %bb1 ]
  %arr1 = phi i8 [ 0, %bb0 ], [ %arr0, %bb1 ]
  %i_read = load volatile i8, ptr addrspace(1) %i, align 1
  store volatile i8 %arr1, ptr addrspace(2) %o, align 1
  br label %bb1
}
