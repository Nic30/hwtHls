define void @ExampleRomPyList.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL76i0_76

blockL76i0_76:                                    ; preds = %block0
  br label %blockL76i0_80

blockL76i0_80:                                    ; preds = %blockL76i0_76
  br label %blockL76i1_76

blockL76i1_76:                                    ; preds = %blockL76i0_80
  br label %blockL76i1_80

blockL76i1_80:                                    ; preds = %blockL76i1_76
  br label %blockL76i2_76

blockL76i2_76:                                    ; preds = %blockL76i1_80
  br label %blockL76i2_80

blockL76i2_80:                                    ; preds = %blockL76i2_76
  br label %blockL76i3_76

blockL76i3_76:                                    ; preds = %blockL76i2_80
  br label %blockL76i3_80

blockL76i3_80:                                    ; preds = %blockL76i3_76
  br label %blockL76i4_76

blockL76i4_76:                                    ; preds = %blockL76i3_80
  br label %block124

block124:                                         ; preds = %blockL76i4_76
  br label %blockL142i0_142

blockL142i0_142:                                  ; preds = %blockL142i0_294, %block124
  %i_read = alloca i2, align 1, !hwtHls.tmp.alloca !2
  store i2 undef, ptr %i_read, align 1
  %o1 = alloca i32, align 4, !hwtHls.tmp.alloca !2
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
  br label %blockL142i0_294

blockL142i0_294:                                  ; preds = %blockL142i0_142
  br label %blockL142i0_142
}
