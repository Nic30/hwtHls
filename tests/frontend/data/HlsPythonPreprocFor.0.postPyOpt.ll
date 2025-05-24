define void @HlsPythonPreprocFor.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL24i0_24

blockL24i0_24:                                    ; preds = %block0
  br label %blockL24i0_28

blockL24i0_28:                                    ; preds = %blockL24i0_24
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL24i1_24

blockL24i1_24:                                    ; preds = %blockL24i0_28
  br label %blockL24i1_28

blockL24i1_28:                                    ; preds = %blockL24i1_24
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL24i2_24

blockL24i2_24:                                    ; preds = %blockL24i1_28
  br label %blockL24i2_28

blockL24i2_28:                                    ; preds = %blockL24i2_24
  store volatile i8 2, ptr addrspace(1) %o, align 1
  br label %blockL24i3_24

blockL24i3_24:                                    ; preds = %blockL24i2_28
  br label %blockL24i3_28

blockL24i3_28:                                    ; preds = %blockL24i3_24
  store volatile i8 3, ptr addrspace(1) %o, align 1
  br label %blockL24i4_24

blockL24i4_24:                                    ; preds = %blockL24i3_28
  br label %blockL24i4_28

blockL24i4_28:                                    ; preds = %blockL24i4_24
  store volatile i8 4, ptr addrspace(1) %o, align 1
  br label %blockL24i5_24

blockL24i5_24:                                    ; preds = %blockL24i4_28
  br label %block88

block88:                                          ; preds = %blockL24i5_24
  ret void
}
