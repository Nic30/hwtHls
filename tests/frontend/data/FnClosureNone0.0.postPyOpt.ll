define void @FnClosureNone0.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL30i0_30

blockL30i0_30:                                    ; preds = %blockL30i0_118, %block0
  store volatile i8 10, ptr addrspace(1) %o, align 1
  br label %blockL30i0_118

blockL30i0_118:                                   ; preds = %blockL30i0_30
  br label %blockL30i0_30
}
