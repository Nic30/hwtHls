define void @HlsPythonSwap.mainThread(ptr addrspace(1) %i0, ptr addrspace(2) %i1, ptr addrspace(3) %o0, ptr addrspace(4) %o1, ptr addrspace(5) %swap) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_408, %block0
  %swap_read = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %swap_read, align 1
  %swap1 = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %swap1, align 1
  %swap_read2 = load volatile i1, ptr addrspace(5) %swap, align 1
  store i1 %swap_read2, ptr %swap_read, align 1
  %swap_read3 = load i1, ptr %swap_read, align 1
  store i1 %swap_read3, ptr %swap1, align 1
  %i0_read = alloca i8, align 1, !hwtHls.tmp.alloca !6
  store i8 undef, ptr %i0_read, align 1
  %i01 = alloca i8, align 1, !hwtHls.tmp.alloca !6
  store i8 undef, ptr %i01, align 1
  %i0_read2 = load volatile i8, ptr addrspace(1) %i0, align 1
  store i8 %i0_read2, ptr %i0_read, align 1
  %i0_read3 = load i8, ptr %i0_read, align 1
  store i8 %i0_read3, ptr %i01, align 1
  %i1_read = alloca i8, align 1, !hwtHls.tmp.alloca !6
  store i8 undef, ptr %i1_read, align 1
  %i11 = alloca i8, align 1, !hwtHls.tmp.alloca !6
  store i8 undef, ptr %i11, align 1
  %i1_read2 = load volatile i8, ptr addrspace(2) %i1, align 1
  store i8 %i1_read2, ptr %i1_read, align 1
  %i1_read3 = load i8, ptr %i1_read, align 1
  store i8 %i1_read3, ptr %i11, align 1
  br i1 %swap_read3, label %blockL14i0_240, label %blockL14i0_284

blockL14i0_240:                                   ; preds = %blockL14i0_14
  %i04 = load i8, ptr %i01, align 1
  %i15 = load i8, ptr %i11, align 1
  store i8 %i15, ptr %i01, align 1
  store i8 %i04, ptr %i11, align 1
  br label %blockL14i0_284

blockL14i0_284:                                   ; preds = %blockL14i0_14, %blockL14i0_240
  %i06 = load i8, ptr %i01, align 1
  store volatile i8 %i06, ptr addrspace(3) %o0, align 1
  %i12 = load i8, ptr %i11, align 1
  store volatile i8 %i12, ptr addrspace(4) %o1, align 1
  br label %blockL14i0_408

blockL14i0_408:                                   ; preds = %blockL14i0_284
  br label %blockL14i0_14
}
