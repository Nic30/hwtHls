define void @WhileAndIf0.mainThread(ptr addrspace(1) %dataOut) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL24i0_24

blockL24i0_24:                                    ; preds = %blockL24i0_236, %block0
  %x = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %x, align 1
  store i8 10, ptr %x, align 1
  br label %blockL24i0_L108i0_108

blockL24i0_L108i0_108:                            ; preds = %blockL24i0_L108i0_210, %blockL24i0_24
  %x1 = load i8, ptr %x, align 1
  %0 = icmp ult i8 %x1, 3
  br i1 %0, label %blockL24i0_L108i0_120, label %blockL24i0_L108i0_132

blockL24i0_L108i0_120:                            ; preds = %blockL24i0_L108i0_108
  %x2 = load i8, ptr %x, align 1
  %1 = sub i8 %x2, 1
  store i8 %1, ptr %x, align 1
  br label %blockL24i0_L108i0_142

blockL24i0_L108i0_142:                            ; preds = %blockL24i0_L108i0_132, %blockL24i0_L108i0_120
  %x3 = load i8, ptr %x, align 1
  store volatile i8 %x3, ptr addrspace(1) %dataOut, align 1
  %2 = icmp ne i8 %x3, 0
  br i1 %2, label %blockL24i0_L108i0_210, label %blockL24i0_214

blockL24i0_L108i0_210:                            ; preds = %blockL24i0_L108i0_142
  br label %blockL24i0_L108i0_108

blockL24i0_L108i0_132:                            ; preds = %blockL24i0_L108i0_108
  %x4 = load i8, ptr %x, align 1
  %3 = sub i8 %x4, 3
  store i8 %3, ptr %x, align 1
  br label %blockL24i0_L108i0_142

blockL24i0_214:                                   ; preds = %blockL24i0_L108i0_142
  br label %blockL24i0_236

blockL24i0_236:                                   ; preds = %blockL24i0_214
  br label %blockL24i0_24
}
