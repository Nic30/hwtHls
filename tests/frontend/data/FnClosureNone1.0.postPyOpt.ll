define void @FnClosureNone1.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL44i0_44

blockL44i0_44:                                    ; preds = %blockL44i0_158, %block0
  store volatile i8 10, ptr addrspace(1) %o, align 1
  br label %blockL44i0_158

blockL44i0_158:                                   ; preds = %blockL44i0_44
  br label %blockL44i0_44
}
