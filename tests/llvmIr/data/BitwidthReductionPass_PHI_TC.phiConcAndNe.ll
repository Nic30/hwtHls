define void @phiConcAndNe(ptr addrspace(1) %aIn, ptr addrspace(2) %bOut) {
bb0:
  br label %bb.header

bb.header:                                        ; preds = %bb.latch, %bb0
  %a = load volatile i1, ptr addrspace(1) %aIn, align 4
  %b = load volatile i1, ptr addrspace(1) %aIn, align 4
  br i1 %a, label %bb.body, label %bb.latch

bb.body:                                          ; preds = %bb.header
  br label %bb.latch

bb.latch:                                         ; preds = %bb.body, %bb.header
  %res_sign = phi i1 [ false, %bb.header ], [ %b, %bb.body ]
  %res_sign.ne1 = xor i1 %res_sign, false
  store volatile i1 %res_sign.ne1, ptr addrspace(2) %bOut, align 4
  br label %bb.header
}
