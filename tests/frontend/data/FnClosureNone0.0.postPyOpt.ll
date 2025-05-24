define void @FnClosureNone0.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL50i0_50

blockL50i0_50:                                    ; preds = %blockL50i0_158, %block0
  store volatile i8 10, ptr addrspace(1) %o, align 1
  br label %blockL50i0_158

blockL50i0_158:                                   ; preds = %blockL50i0_50
  br label %blockL50i0_50
}
