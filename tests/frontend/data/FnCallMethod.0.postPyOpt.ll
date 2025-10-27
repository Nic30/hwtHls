define void @FnCallMethod.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL56i0_56

blockL56i0_56:                                    ; preds = %blockL56i0_134, %block0
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL56i0_134

blockL56i0_134:                                   ; preds = %blockL56i0_56
  br label %blockL56i0_56
}
