define void @WhileAndIf2.mainThread(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL24i0_24

blockL24i0_24:                                    ; preds = %blockL24i0_280, %block0
  %x = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %x, align 1
  store i8 10, ptr %x, align 1
  br label %blockL24i0_L108i0_108

blockL24i0_L108i0_108:                            ; preds = %blockL24i0_L108i0_254, %blockL24i0_24
  %dataIn_read = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %dataIn_read, align 1
  %x1 = load i8, ptr %x, align 1
  %dataIn_read1 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  store i8 %dataIn_read1, ptr %dataIn_read, align 1
  %dataIn_read2 = load i8, ptr %dataIn_read, align 1
  %0 = sub i8 %x1, %dataIn_read2
  store i8 %0, ptr %x, align 1
  store volatile i8 %0, ptr addrspace(2) %dataOut, align 1
  %1 = icmp ne i8 %0, 0
  br i1 %1, label %blockL24i0_L108i0_254, label %blockL24i0_258

blockL24i0_L108i0_254:                            ; preds = %blockL24i0_L108i0_108
  br label %blockL24i0_L108i0_108

blockL24i0_258:                                   ; preds = %blockL24i0_L108i0_108
  br label %blockL24i0_280

blockL24i0_280:                                   ; preds = %blockL24i0_258
  br label %blockL24i0_24
}
