define void @FnCallFn.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL44i0_44

blockL44i0_44:                                    ; preds = %blockL44i0_122, %block0
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL44i0_122

blockL44i0_122:                                   ; preds = %blockL44i0_44
  br label %blockL44i0_44
}
