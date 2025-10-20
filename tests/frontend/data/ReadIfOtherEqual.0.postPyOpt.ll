define void @ReadIfOtherEqual.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_184, %block0
  %a_read = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %a_read, align 1
  %a_read1 = load volatile i8, ptr addrspace(1) %a, align 1
  store i8 %a_read1, ptr %a_read, align 1
  %a_read2 = load i8, ptr %a_read, align 1
  %0 = icmp eq i8 %a_read2, 3
  br i1 %0, label %blockL14i0_118, label %blockL14i0_172

blockL14i0_118:                                   ; preds = %blockL14i0_14
  %b_read = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %b_read, align 1
  %b_read1 = load volatile i8, ptr addrspace(2) %b, align 1
  store i8 %b_read1, ptr %b_read, align 1
  br label %blockL14i0_172

blockL14i0_172:                                   ; preds = %blockL14i0_14, %blockL14i0_118
  br label %blockL14i0_184

blockL14i0_184:                                   ; preds = %blockL14i0_172
  br label %blockL14i0_14
}
