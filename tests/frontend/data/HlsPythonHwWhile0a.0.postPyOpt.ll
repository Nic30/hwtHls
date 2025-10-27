define void @HlsPythonHwWhile0a.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i1 = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i1, align 1
  store i8 0, ptr %i1, align 1
  br label %blockL68i0_68

blockL68i0_68:                                    ; preds = %blockL68i0_242, %block0
  %i12 = load i8, ptr %i1, align 1
  %0 = add i8 %i12, 1
  store i8 %0, ptr %i1, align 1
  store volatile i8 %0, ptr addrspace(2) %o, align 1
  %i_read = alloca i1, align 1, !hwtHls.tmp.alloca !3
  store i1 undef, ptr %i_read, align 1
  %i_read3 = load volatile i1, ptr addrspace(1) %i, align 1
  store i1 %i_read3, ptr %i_read, align 1
  %i_read4 = load i1, ptr %i_read, align 1
  br i1 %i_read4, label %blockL68i0_216, label %blockL68i0_220

blockL68i0_216:                                   ; preds = %blockL68i0_68
  store i8 0, ptr %i1, align 1
  br label %blockL68i0_220

blockL68i0_220:                                   ; preds = %blockL68i0_68, %blockL68i0_216
  br label %blockL68i0_242

blockL68i0_242:                                   ; preds = %blockL68i0_220
  br label %blockL68i0_68
}
