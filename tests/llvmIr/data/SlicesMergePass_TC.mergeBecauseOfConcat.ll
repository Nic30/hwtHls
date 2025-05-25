define void @mergeBecauseOfConcat(ptr addrspace(1) %i, ptr addrspace(2) %o) {
BB0:
  %i0 = load volatile i8, ptr addrspace(1) %i, align 1
  br label %BB1

BB1:                                              ; preds = %BB1, %BB0
  store volatile i8 %i0, ptr addrspace(2) %o, align 1
  br label %BB1
}
