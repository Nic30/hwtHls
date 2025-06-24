define void @FnClosureNone0.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL20i0_20

blockL20i0_20:                                    ; preds = %blockL20i0_98, %block0
  store volatile i8 10, ptr addrspace(1) %o, align 1
  br label %blockL20i0_98

blockL20i0_98:                                    ; preds = %blockL20i0_20
  br label %blockL20i0_20
}
