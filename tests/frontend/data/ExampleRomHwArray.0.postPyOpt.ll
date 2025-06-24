define void @ExampleRomHwArray.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL100i0_100

blockL100i0_100:                                  ; preds = %block0
  br label %blockL100i0_104

blockL100i0_104:                                  ; preds = %blockL100i0_100
  br label %blockL100i1_100

blockL100i1_100:                                  ; preds = %blockL100i0_104
  br label %blockL100i1_104

blockL100i1_104:                                  ; preds = %blockL100i1_100
  br label %blockL100i2_100

blockL100i2_100:                                  ; preds = %blockL100i1_104
  br label %blockL100i2_104

blockL100i2_104:                                  ; preds = %blockL100i2_100
  br label %blockL100i3_100

blockL100i3_100:                                  ; preds = %blockL100i2_104
  br label %blockL100i3_104

blockL100i3_104:                                  ; preds = %blockL100i3_100
  br label %blockL100i4_100

blockL100i4_100:                                  ; preds = %blockL100i3_104
  br label %block118

block118:                                         ; preds = %blockL100i4_100
  %mem = alloca [4 x i32], align 4, !hwtHls.tmp.alloca !4
  store [4 x i32] undef, ptr %mem, align 4
  call void @llvm.memcpy.p0.p0.i64(ptr align 1 %mem, ptr align 1 @0, i64 16, i1 false)
  br label %blockL146i0_146

blockL146i0_146:                                  ; preds = %blockL146i0_298, %block118
  %i_read = alloca i2, align 1, !hwtHls.tmp.alloca !4
  store i2 undef, ptr %i_read, align 1
  %o1 = alloca i32, align 4, !hwtHls.tmp.alloca !4
  store i32 undef, ptr %o1, align 4
  %i_read1 = load volatile i2, ptr addrspace(1) %i, align 1
  store i2 %i_read1, ptr %i_read, align 1
  %i_read2 = load i2, ptr %i_read, align 1
  %0 = zext i2 %i_read2 to i64
  %1 = getelementptr inbounds [4 x i32], ptr %mem, i64 0, i64 %0
  %o3 = load i32, ptr %1, align 4
  store i32 %o3, ptr %o1, align 4
  store volatile i32 %o3, ptr addrspace(2) %o, align 4
  br label %blockL146i0_298

blockL146i0_298:                                  ; preds = %blockL146i0_146
  br label %blockL146i0_146
}
