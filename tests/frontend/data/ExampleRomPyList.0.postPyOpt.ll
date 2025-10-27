define void @ExampleRomPyList.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL78i0_78

blockL78i0_78:                                    ; preds = %block0
  br label %blockL78i0_82

blockL78i0_82:                                    ; preds = %blockL78i0_78
  br label %blockL78i1_78

blockL78i1_78:                                    ; preds = %blockL78i0_82
  br label %blockL78i1_82

blockL78i1_82:                                    ; preds = %blockL78i1_78
  br label %blockL78i2_78

blockL78i2_78:                                    ; preds = %blockL78i1_82
  br label %blockL78i2_82

blockL78i2_82:                                    ; preds = %blockL78i2_78
  br label %blockL78i3_78

blockL78i3_78:                                    ; preds = %blockL78i2_82
  br label %blockL78i3_82

blockL78i3_82:                                    ; preds = %blockL78i3_78
  br label %blockL78i4_78

blockL78i4_78:                                    ; preds = %blockL78i3_82
  br label %block126

block126:                                         ; preds = %blockL78i4_78
  br label %blockL156i0_156

blockL156i0_156:                                  ; preds = %blockL156i0_314, %block126
  %i_read = alloca i2, align 1, !hwtHls.tmp.alloca !3
  store i2 undef, ptr %i_read, align 1
  %o1 = alloca i32, align 4, !hwtHls.tmp.alloca !3
  store i32 undef, ptr %o1, align 4
  %i_read1 = load volatile i2, ptr addrspace(1) %i, align 1
  store i2 %i_read1, ptr %i_read, align 1
  %i_read2 = load i2, ptr %i_read, align 1
  %0 = icmp eq i2 %i_read2, 0
  %1 = icmp eq i2 %i_read2, 1
  %2 = icmp eq i2 %i_read2, -2
  %3 = select i1 %2, i32 4, i32 8
  %4 = select i1 %1, i32 2, i32 %3
  %o3 = select i1 %0, i32 1, i32 %4
  store i32 %o3, ptr %o1, align 4
  store volatile i32 %o3, ptr addrspace(2) %o, align 4
  br label %blockL156i0_314

blockL156i0_314:                                  ; preds = %blockL156i0_156
  br label %blockL156i0_156
}
