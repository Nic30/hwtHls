define void @WhileAndIf4.mainThread(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL24i0_24

blockL24i0_24:                                    ; preds = %block0
  %x = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %x, align 1
  store i8 10, ptr %x, align 1
  br label %blockL24i0_L116i0_116

blockL24i0_L116i0_116:                            ; preds = %blockL24i0_L116i0_282, %blockL24i0_24
  %dataIn_read = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %dataIn_read, align 1
  %x1 = load i8, ptr %x, align 1
  %dataIn_read1 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  store i8 %dataIn_read1, ptr %dataIn_read, align 1
  %dataIn_read2 = load i8, ptr %dataIn_read, align 1
  %0 = sub i8 %x1, %dataIn_read2
  store i8 %0, ptr %x, align 1
  %1 = icmp ult i8 %0, 5
  br i1 %1, label %blockL24i0_L116i0_206, label %blockL24i0_L116i0_260

blockL24i0_L116i0_206:                            ; preds = %blockL24i0_L116i0_116
  %x3 = load i8, ptr %x, align 1
  store volatile i8 %x3, ptr addrspace(2) %dataOut, align 1
  br label %blockL24i0_L116i0_260

blockL24i0_L116i0_260:                            ; preds = %blockL24i0_L116i0_116, %blockL24i0_L116i0_206
  br label %blockL24i0_L116i0_282

blockL24i0_L116i0_282:                            ; preds = %blockL24i0_L116i0_260
  br label %blockL24i0_L116i0_116
}
