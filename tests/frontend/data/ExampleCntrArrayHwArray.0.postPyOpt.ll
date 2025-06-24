define void @ExampleCntrArrayHwArray.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %o_addr) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL140i0_140

blockL140i0_140:                                  ; preds = %block0
  br label %blockL140i0_144

blockL140i0_144:                                  ; preds = %blockL140i0_140
  br label %blockL140i1_140

blockL140i1_140:                                  ; preds = %blockL140i0_144
  br label %blockL140i1_144

blockL140i1_144:                                  ; preds = %blockL140i1_140
  br label %blockL140i2_140

blockL140i2_140:                                  ; preds = %blockL140i1_144
  br label %blockL140i2_144

blockL140i2_144:                                  ; preds = %blockL140i2_140
  br label %blockL140i3_140

blockL140i3_140:                                  ; preds = %blockL140i2_144
  br label %blockL140i3_144

blockL140i3_144:                                  ; preds = %blockL140i3_140
  br label %blockL140i4_140

blockL140i4_140:                                  ; preds = %blockL140i3_144
  br label %block152

block152:                                         ; preds = %blockL140i4_140
  %mem = alloca [4 x i16], align 2, !hwtHls.tmp.alloca !2
  store [4 x i16] undef, ptr %mem, align 2
  call void @llvm.memcpy.p0.p0.i64(ptr align 1 %mem, ptr align 1 @0, i64 8, i1 false)
  br label %blockL180i0_180

blockL180i0_180:                                  ; preds = %blockL180i0_428, %block152
  %o_addr_read = alloca i2, align 1, !hwtHls.tmp.alloca !2
  store i2 undef, ptr %o_addr_read, align 1
  %o1 = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %o1, align 2
  %o_addr_read1 = load volatile i2, ptr addrspace(3) %o_addr, align 1
  store i2 %o_addr_read1, ptr %o_addr_read, align 1
  %o_addr_read2 = load i2, ptr %o_addr_read, align 1
  %0 = zext i2 %o_addr_read2 to i64
  %1 = getelementptr inbounds [4 x i16], ptr %mem, i64 0, i64 %0
  %o3 = load i16, ptr %1, align 2
  store i16 %o3, ptr %o1, align 2
  %i_read = alloca i2, align 1, !hwtHls.tmp.alloca !2
  store i2 undef, ptr %i_read, align 1
  %i1 = alloca i2, align 1, !hwtHls.tmp.alloca !2
  store i2 undef, ptr %i1, align 1
  %i_read2 = load volatile i2, ptr addrspace(1) %i, align 1
  store i2 %i_read2, ptr %i_read, align 1
  %i_read3 = load i2, ptr %i_read, align 1
  store i2 %i_read3, ptr %i1, align 1
  store volatile i16 %o3, ptr addrspace(2) %o, align 2
  %2 = zext i2 %i_read3 to i64
  %3 = getelementptr inbounds [4 x i16], ptr %mem, i64 0, i64 %2
  %4 = load i16, ptr %3, align 2
  %5 = add i16 %4, 1
  %6 = zext i2 %i_read3 to i64
  %7 = getelementptr inbounds [4 x i16], ptr %mem, i64 0, i64 %6
  store i16 %5, ptr %7, align 2
  br label %blockL180i0_428

blockL180i0_428:                                  ; preds = %blockL180i0_180
  br label %blockL180i0_180
}
