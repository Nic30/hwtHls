define void @optionalStore0(ptr addrspace(1) %o) {
entry:
  br label %bb0

bb0:                                              ; preds = %bb2, %entry
  %i = phi i1 [ false, %entry ], [ %i.not, %bb2 ]
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br i1 %i, label %bb2, label %bb1

bb1:                                              ; preds = %bb0
  store volatile i8 2, ptr addrspace(1) %o, align 1
  br label %bb2

bb2:                                              ; preds = %bb1, %bb0
  %i.not = xor i1 %i, true
  store volatile i8 3, ptr addrspace(1) %o, align 1
  br label %bb0
}
