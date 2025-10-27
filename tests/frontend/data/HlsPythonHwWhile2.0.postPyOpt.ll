define void @HlsPythonHwWhile2.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i, align 1
  store i8 0, ptr %i, align 1
  br label %wh0

wh0:                                              ; preds = %blockL68i0_236, %block0
  %i1 = load i8, ptr %i, align 1
  %0 = icmp ule i8 %i1, 4
  br i1 %0, label %blockL68i0_102, label %blockL68i0_158

blockL68i0_102:                                   ; preds = %wh0
  %i2 = load i8, ptr %i, align 1
  store volatile i8 %i2, ptr addrspace(1) %o, align 1
  br label %blockL68i0_204

blockL68i0_204:                                   ; preds = %blockL68i0_158, %blockL68i0_102
  %i3 = load i8, ptr %i, align 1
  %1 = add i8 %i3, 1
  store i8 %1, ptr %i, align 1
  br label %blockL68i0_236

blockL68i0_236:                                   ; preds = %blockL68i0_204
  br label %wh0

blockL68i0_158:                                   ; preds = %wh0
  %i4 = load i8, ptr %i, align 1
  %2 = icmp eq i8 %i4, 10
  br i1 %2, label %block202, label %blockL68i0_204

block202:                                         ; preds = %blockL68i0_158
  br label %block240

block240:                                         ; preds = %block202
  br label %wh1

wh1:                                              ; preds = %blockL262i0_362, %block240
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL262i0_362

blockL262i0_362:                                  ; preds = %wh1
  br label %wh1
}
