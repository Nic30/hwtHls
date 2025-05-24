define void @VariableChain.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL52i0_52

blockL52i0_52:                                    ; preds = %block0
  br label %blockL52i0_56

blockL52i0_56:                                    ; preds = %blockL52i0_52
  %i0 = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i0, align 1
  br label %blockL52i1_52

blockL52i1_52:                                    ; preds = %blockL52i0_56
  br label %blockL52i1_56

blockL52i1_56:                                    ; preds = %blockL52i1_52
  %i1 = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i1, align 1
  br label %blockL52i2_52

blockL52i2_52:                                    ; preds = %blockL52i1_56
  br label %blockL52i2_56

blockL52i2_56:                                    ; preds = %blockL52i2_52
  %i2 = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i2, align 1
  br label %blockL52i3_52

blockL52i3_52:                                    ; preds = %blockL52i2_56
  br label %block144

block144:                                         ; preds = %blockL52i3_52
  br label %blockL162i0_162

blockL162i0_162:                                  ; preds = %blockL162i0_392, %block144
  br label %blockL162i0_L184i0_184

blockL162i0_L184i0_184:                           ; preds = %blockL162i0_162
  br label %blockL162i0_L184i0_188

blockL162i0_L184i0_188:                           ; preds = %blockL162i0_L184i0_184
  br label %blockL162i0_L184i0_206

blockL162i0_L184i0_206:                           ; preds = %blockL162i0_L184i0_188
  %i_read = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i_read, align 1
  %prev = alloca i8, align 1, !hwtHls.tmp.alloca !2
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
  br label %blockL162i0_L184i1_188

blockL162i0_L184i1_188:                           ; preds = %blockL162i0_L184i1_184
  br label %blockL162i0_L184i1_282

blockL162i0_L184i1_282:                           ; preds = %blockL162i0_L184i1_188
  %i04 = load i8, ptr %i0, align 1
  store i8 %i04, ptr %prev, align 1
  br label %blockL162i0_L184i1_298

blockL162i0_L184i1_298:                           ; preds = %blockL162i0_L184i1_282
  %prev5 = load i8, ptr %prev, align 1
  store i8 %prev5, ptr %i1, align 1
  br label %blockL162i0_L184i2_184

blockL162i0_L184i2_184:                           ; preds = %blockL162i0_L184i1_298
  br label %blockL162i0_L184i2_188

blockL162i0_L184i2_188:                           ; preds = %blockL162i0_L184i2_184
  br label %blockL162i0_L184i2_282

blockL162i0_L184i2_282:                           ; preds = %blockL162i0_L184i2_188
  %i16 = load i8, ptr %i1, align 1
  store i8 %i16, ptr %prev, align 1
  br label %blockL162i0_L184i2_298

blockL162i0_L184i2_298:                           ; preds = %blockL162i0_L184i2_282
  %prev7 = load i8, ptr %prev, align 1
  store i8 %prev7, ptr %i2, align 1
  br label %blockL162i0_L184i3_184

blockL162i0_L184i3_184:                           ; preds = %blockL162i0_L184i2_298
  br label %blockL162i0_316

blockL162i0_316:                                  ; preds = %blockL162i0_L184i3_184
  %i28 = load i8, ptr %i2, align 1
  store volatile i8 %i28, ptr addrspace(2) %o, align 1
  br label %blockL162i0_392

blockL162i0_392:                                  ; preds = %blockL162i0_316
  br label %blockL162i0_162
}
