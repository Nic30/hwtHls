define void @HlsPythonPreprocForInIf0.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %block116

block116:                                         ; preds = %block0
  br label %blockL138i0_138

blockL138i0_138:                                  ; preds = %block116
  br label %blockL138i0_142

blockL138i0_142:                                  ; preds = %blockL138i0_138
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL138i1_138

blockL138i1_138:                                  ; preds = %blockL138i0_142
  br label %blockL138i1_142

blockL138i1_142:                                  ; preds = %blockL138i1_138
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL138i2_138

blockL138i2_138:                                  ; preds = %blockL138i1_142
  br label %blockL138i2_142

blockL138i2_142:                                  ; preds = %blockL138i2_138
  store volatile i8 2, ptr addrspace(1) %o, align 1
  br label %blockL138i3_138

blockL138i3_138:                                  ; preds = %blockL138i2_142
  br label %block202

block202:                                         ; preds = %blockL138i3_138
  ret void
}
