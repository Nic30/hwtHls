define void @HlsPythonPreprocForPreprocWhile.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL24i0_24

blockL24i0_24:                                    ; preds = %block0
  br label %blockL24i0_28

blockL24i0_28:                                    ; preds = %blockL24i0_24
  br label %blockL24i0_L42i0_42

blockL24i0_L42i0_42:                              ; preds = %blockL24i0_L42i0_118, %blockL24i0_28
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL24i0_L42i0_118

blockL24i0_L42i0_118:                             ; preds = %blockL24i0_L42i0_42
  br label %blockL24i0_L42i0_42
}
