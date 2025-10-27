define void @FnCallFnKwArgs.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL24i0_24

blockL24i0_24:                                    ; preds = %blockL24i0_120, %block0
  store volatile i8 10, ptr addrspace(1) %o, align 1
  br label %blockL24i0_120

blockL24i0_120:                                   ; preds = %blockL24i0_24
  br label %blockL24i0_24
}
