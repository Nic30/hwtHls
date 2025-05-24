define void @TwoTimesA0.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_162, %block0
  %a_read = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %a_read, align 1
  %a1 = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %a1, align 1
  %a_read2 = load volatile i8, ptr addrspace(1) %a, align 1
  store i8 %a_read2, ptr %a_read, align 1
  %a_read3 = load i8, ptr %a_read, align 1
  store i8 %a_read3, ptr %a1, align 1
  %0 = add i8 %a_read3, %a_read3
  store volatile i8 %0, ptr addrspace(2) %b, align 1
  br label %blockL14i0_162

blockL14i0_162:                                   ; preds = %blockL14i0_14
  br label %blockL14i0_14
}
