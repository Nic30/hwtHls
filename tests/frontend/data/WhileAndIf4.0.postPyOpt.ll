define void @WhileAndIf4.mainThread(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %block0
  %x = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %x, align 1
  store i8 10, ptr %x, align 1
  br label %blockL14i0_L102i0_102

blockL14i0_L102i0_102:                            ; preds = %blockL14i0_L102i0_260, %blockL14i0_14
  %dataIn_read = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %dataIn_read, align 1
  %x1 = load i8, ptr %x, align 1
  %dataIn_read1 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  store i8 %dataIn_read1, ptr %dataIn_read, align 1
  %dataIn_read2 = load i8, ptr %dataIn_read, align 1
  %0 = sub i8 %x1, %dataIn_read2
  store i8 %0, ptr %x, align 1
  %1 = icmp ult i8 %0, 5
  br i1 %1, label %blockL14i0_L102i0_192, label %blockL14i0_L102i0_248

blockL14i0_L102i0_192:                            ; preds = %blockL14i0_L102i0_102
  %x3 = load i8, ptr %x, align 1
  store volatile i8 %x3, ptr addrspace(2) %dataOut, align 1
  br label %blockL14i0_L102i0_248

blockL14i0_L102i0_248:                            ; preds = %blockL14i0_L102i0_102, %blockL14i0_L102i0_192
  br label %blockL14i0_L102i0_260

blockL14i0_L102i0_260:                            ; preds = %blockL14i0_L102i0_248
  br label %blockL14i0_L102i0_102
}
