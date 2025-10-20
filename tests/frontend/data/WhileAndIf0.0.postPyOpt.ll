define void @WhileAndIf0.mainThread(ptr addrspace(1) %dataOut) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_200, %block0
  %x = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %x, align 1
  store i8 10, ptr %x, align 1
  br label %blockL14i0_L94i0_94

blockL14i0_L94i0_94:                              ; preds = %blockL14i0_L94i0_186, %blockL14i0_14
  %x1 = load i8, ptr %x, align 1
  %0 = icmp ult i8 %x1, 3
  br i1 %0, label %blockL14i0_L94i0_104, label %blockL14i0_L94i0_116

blockL14i0_L94i0_104:                             ; preds = %blockL14i0_L94i0_94
  %x2 = load i8, ptr %x, align 1
  %1 = sub i8 %x2, 1
  store i8 %1, ptr %x, align 1
  br label %blockL14i0_L94i0_126

blockL14i0_L94i0_126:                             ; preds = %blockL14i0_L94i0_116, %blockL14i0_L94i0_104
  %x3 = load i8, ptr %x, align 1
  store volatile i8 %x3, ptr addrspace(1) %dataOut, align 1
  %2 = icmp ne i8 %x3, 0
  br i1 %2, label %blockL14i0_L94i0_186, label %blockL14i0_188

blockL14i0_L94i0_186:                             ; preds = %blockL14i0_L94i0_126
  br label %blockL14i0_L94i0_94

blockL14i0_L94i0_116:                             ; preds = %blockL14i0_L94i0_94
  %x4 = load i8, ptr %x, align 1
  %3 = sub i8 %x4, 3
  store i8 %3, ptr %x, align 1
  br label %blockL14i0_L94i0_126

blockL14i0_188:                                   ; preds = %blockL14i0_L94i0_126
  br label %blockL14i0_200

blockL14i0_200:                                   ; preds = %blockL14i0_188
  br label %blockL14i0_14
}
