define void @HlsPythonHwWhile2.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i, align 1
  store i8 0, ptr %i, align 1
  br label %wh0

wh0:                                              ; preds = %blockL56i0_204, %block0
  %i1 = load i8, ptr %i, align 1
  %0 = icmp ule i8 %i1, 4
  br i1 %0, label %blockL56i0_88, label %blockL56i0_146

blockL56i0_88:                                    ; preds = %wh0
  %i2 = load i8, ptr %i, align 1
  store volatile i8 %i2, ptr addrspace(1) %o, align 1
  br label %blockL56i0_182

blockL56i0_182:                                   ; preds = %blockL56i0_146, %blockL56i0_88
  %i3 = load i8, ptr %i, align 1
  %1 = add i8 %i3, 1
  store i8 %1, ptr %i, align 1
  br label %blockL56i0_204

blockL56i0_204:                                   ; preds = %blockL56i0_182
  br label %wh0

blockL56i0_146:                                   ; preds = %wh0
  %i4 = load i8, ptr %i, align 1
  %2 = icmp eq i8 %i4, 10
  br i1 %2, label %block180, label %blockL56i0_182

block180:                                         ; preds = %blockL56i0_146
  br label %block206

block206:                                         ; preds = %block180
  br label %wh1

wh1:                                              ; preds = %blockL218i0_308, %block206
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL218i0_308

blockL218i0_308:                                  ; preds = %wh1
  br label %wh1
}
