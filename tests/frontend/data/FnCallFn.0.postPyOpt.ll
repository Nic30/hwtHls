define void @FnCallFn.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL34i0_34

blockL34i0_34:                                    ; preds = %blockL34i0_102, %block0
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL34i0_102

blockL34i0_102:                                   ; preds = %blockL34i0_34
  br label %blockL34i0_34
}
