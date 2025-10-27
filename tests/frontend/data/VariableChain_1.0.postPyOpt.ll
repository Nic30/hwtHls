define void @VariableChain.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL54i0_54

blockL54i0_54:                                    ; preds = %block0
  br label %blockL54i0_58

blockL54i0_58:                                    ; preds = %blockL54i0_54
  %i0 = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i0, align 1
  br label %blockL54i1_54

blockL54i1_54:                                    ; preds = %blockL54i0_58
  br label %block146

block146:                                         ; preds = %blockL54i1_54
  br label %blockL176i0_176

blockL176i0_176:                                  ; preds = %blockL176i0_418, %block146
  br label %blockL176i0_L198i0_198

blockL176i0_L198i0_198:                           ; preds = %blockL176i0_176
  br label %blockL176i0_L198i0_202

blockL176i0_L198i0_202:                           ; preds = %blockL176i0_L198i0_198
  br label %blockL176i0_L198i0_220

blockL176i0_L198i0_220:                           ; preds = %blockL176i0_L198i0_202
  %i_read = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i_read, align 1
  %prev = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %prev, align 1
  %i_read1 = load volatile i8, ptr addrspace(1) %i, align 1
  store i8 %i_read1, ptr %i_read, align 1
  %i_read2 = load i8, ptr %i_read, align 1
  store i8 %i_read2, ptr %prev, align 1
  br label %blockL176i0_L198i0_310

blockL176i0_L198i0_310:                           ; preds = %blockL176i0_L198i0_220
  %prev3 = load i8, ptr %prev, align 1
  store i8 %prev3, ptr %i0, align 1
  br label %blockL176i0_L198i1_198

blockL176i0_L198i1_198:                           ; preds = %blockL176i0_L198i0_310
  br label %blockL176i0_330

blockL176i0_330:                                  ; preds = %blockL176i0_L198i1_198
  %i04 = load i8, ptr %i0, align 1
  store volatile i8 %i04, ptr addrspace(2) %o, align 1
  br label %blockL176i0_418

blockL176i0_418:                                  ; preds = %blockL176i0_330
  br label %blockL176i0_176
}
