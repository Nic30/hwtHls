define void @ExampleRomHwArray.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL102i0_102

blockL102i0_102:                                  ; preds = %block0
  br label %blockL102i0_106

blockL102i0_106:                                  ; preds = %blockL102i0_102
  br label %blockL102i1_102

blockL102i1_102:                                  ; preds = %blockL102i0_106
  br label %blockL102i1_106

blockL102i1_106:                                  ; preds = %blockL102i1_102
  br label %blockL102i2_102

blockL102i2_102:                                  ; preds = %blockL102i1_106
  br label %blockL102i2_106

blockL102i2_106:                                  ; preds = %blockL102i2_102
  br label %blockL102i3_102

blockL102i3_102:                                  ; preds = %blockL102i2_106
  br label %blockL102i3_106

blockL102i3_106:                                  ; preds = %blockL102i3_102
  br label %blockL102i4_102

blockL102i4_102:                                  ; preds = %blockL102i3_106
  br label %block122

block122:                                         ; preds = %blockL102i4_102
  %mem = alloca [4 x i32], align 4, !hwtHls.tmp.alloca !3
  store [4 x i32] undef, ptr %mem, align 4
  call void @llvm.memcpy.p0.p0.i64(ptr align 1 %mem, ptr align 1 @0, i64 16, i1 false)
  br label %blockL162i0_162

blockL162i0_162:                                  ; preds = %blockL162i0_320, %block122
  %i_read = alloca i2, align 1, !hwtHls.tmp.alloca !3
  store i2 undef, ptr %i_read, align 1
  %o1 = alloca i32, align 4, !hwtHls.tmp.alloca !3
  store i32 undef, ptr %o1, align 4
  %i_read1 = load volatile i2, ptr addrspace(1) %i, align 1
  store i2 %i_read1, ptr %i_read, align 1
  %i_read2 = load i2, ptr %i_read, align 1
  %0 = zext i2 %i_read2 to i64
  %1 = getelementptr inbounds [4 x i32], ptr %mem, i64 0, i64 %0
  %o3 = load i32, ptr %1, align 4
  store i32 %o3, ptr %o1, align 4
  store volatile i32 %o3, ptr addrspace(2) %o, align 4
  br label %blockL162i0_320

blockL162i0_320:                                  ; preds = %blockL162i0_162
  br label %blockL162i0_162
}
