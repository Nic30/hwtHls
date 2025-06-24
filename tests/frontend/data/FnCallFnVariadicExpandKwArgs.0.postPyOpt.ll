define void @FnCallFnVariadicExpandKwArgs.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_106, %block0
  store volatile i8 10, ptr addrspace(1) %o, align 1
  br label %blockL14i0_106

blockL14i0_106:                                   ; preds = %blockL14i0_14
  br label %blockL14i0_14
}
