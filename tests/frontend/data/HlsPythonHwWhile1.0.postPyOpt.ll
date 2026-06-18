define void @HlsPythonHwWhile1.mainThread(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i, align 1
  store i8 10, ptr %i, align 1
  br label %blockL68i0_68

blockL68i0_68:                                    ; preds = %blockL68i0_250, %block0
  br label %blockL68i0_L70i0_70

blockL68i0_L70i0_70:                              ; preds = %blockL68i0_L70i0_220, %blockL68i0_68
  %i1 = load i8, ptr %i, align 1
  store volatile i8 %i1, ptr addrspace(2) %dataOut, align 1
  %0 = add i8 %i1, 1
  store i8 %0, ptr %i, align 1
  %dataIn_read = alloca i1, align 1, !hwtHls.tmp.alloca !3
  store i1 undef, ptr %dataIn_read, align 1
  %dataIn_read1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  store i1 %dataIn_read1, ptr %dataIn_read, align 1
  %dataIn_read2 = load i1, ptr %dataIn_read, align 1
  br i1 %dataIn_read2, label %blockL68i0_218, label %blockL68i0_L70i0_220

blockL68i0_L70i0_220:                             ; preds = %blockL68i0_L70i0_70
  br label %blockL68i0_L70i0_70

blockL68i0_218:                                   ; preds = %blockL68i0_L70i0_70
  br label %blockL68i0_224

blockL68i0_224:                                   ; preds = %blockL68i0_218
  store i8 0, ptr %i, align 1
  br label %blockL68i0_250

blockL68i0_250:                                   ; preds = %blockL68i0_224
  br label %blockL68i0_68
}
