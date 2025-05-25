define void @constInConcat0(ptr addrspace(1) %dataOut) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  store volatile i19 -196607, ptr addrspace(1) %dataOut, align 4
  br label %bb1
}
