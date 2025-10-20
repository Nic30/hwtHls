define void @VariableChain.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL52i0_52

blockL52i0_52:                                    ; preds = %block0
  br label %blockL52i0_56

blockL52i0_56:                                    ; preds = %blockL52i0_52
  %i0 = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i0, align 1
  br label %blockL52i1_52

blockL52i1_52:                                    ; preds = %blockL52i0_56
  br label %block144

block144:                                         ; preds = %blockL52i1_52
  br label %blockL162i0_162

blockL162i0_162:                                  ; preds = %blockL162i0_392, %block144
  br label %blockL162i0_L184i0_184

blockL162i0_L184i0_184:                           ; preds = %blockL162i0_162
  br label %blockL162i0_L184i0_188

blockL162i0_L184i0_188:                           ; preds = %blockL162i0_L184i0_184
  br label %blockL162i0_L184i0_206

blockL162i0_L184i0_206:                           ; preds = %blockL162i0_L184i0_188
  %i_read = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i_read, align 1
  %prev = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %prev, align 1
  %i_read1 = load volatile i8, ptr addrspace(1) %i, align 1
  store i8 %i_read1, ptr %i_read, align 1
  %i_read2 = load i8, ptr %i_read, align 1
  store i8 %i_read2, ptr %prev, align 1
  br label %blockL162i0_L184i0_298

blockL162i0_L184i0_298:                           ; preds = %blockL162i0_L184i0_206
  %prev3 = load i8, ptr %prev, align 1
  store i8 %prev3, ptr %i0, align 1
  br label %blockL162i0_L184i1_184

blockL162i0_L184i1_184:                           ; preds = %blockL162i0_L184i0_298
  br label %blockL162i0_316

blockL162i0_316:                                  ; preds = %blockL162i0_L184i1_184
  %i04 = load i8, ptr %i0, align 1
  store volatile i8 %i04, ptr addrspace(2) %o, align 1
  br label %blockL162i0_392

blockL162i0_392:                                  ; preds = %blockL162i0_316
  br label %blockL162i0_162
}
