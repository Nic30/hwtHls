define void @HlsPythonPreprocForPreprocWhile.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL24i0_24

blockL24i0_24:                                    ; preds = %block0
  br label %blockL24i0_28

blockL24i0_28:                                    ; preds = %blockL24i0_24
  br label %blockL24i0_L46i0_46

blockL24i0_L46i0_46:                              ; preds = %blockL24i0_L46i0_122, %blockL24i0_28
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL24i0_L46i0_122

blockL24i0_L46i0_122:                             ; preds = %blockL24i0_L46i0_46
  br label %blockL24i0_L46i0_46
}
