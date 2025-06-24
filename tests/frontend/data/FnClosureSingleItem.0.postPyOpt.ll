define void @FnClosureSingleItem.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL26i0_26

blockL26i0_26:                                    ; preds = %blockL26i0_126, %block0
  %i_read = alloca i8, align 1, !hwtHls.tmp.alloca !4
  store i8 undef, ptr %i_read, align 1
  %i_read1 = load volatile i8, ptr addrspace(1) %i, align 1
  store i8 %i_read1, ptr %i_read, align 1
  %i_read2 = load i8, ptr %i_read, align 1
  store volatile i8 %i_read2, ptr addrspace(2) %o, align 1
  br label %blockL26i0_126

blockL26i0_126:                                   ; preds = %blockL26i0_26
  br label %blockL26i0_26
}
