define void @FnCallMethod.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL46i0_46

blockL46i0_46:                                    ; preds = %blockL46i0_114, %block0
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL46i0_114

blockL46i0_114:                                   ; preds = %blockL46i0_46
  br label %blockL46i0_46
}
