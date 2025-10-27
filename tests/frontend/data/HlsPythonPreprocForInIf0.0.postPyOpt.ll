define void @HlsPythonPreprocForInIf0.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %block36

block36:                                          ; preds = %block0
  br label %blockL58i0_58

blockL58i0_58:                                    ; preds = %block36
  br label %blockL58i0_62

blockL58i0_62:                                    ; preds = %blockL58i0_58
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL58i1_58

blockL58i1_58:                                    ; preds = %blockL58i0_62
  br label %blockL58i1_62

blockL58i1_62:                                    ; preds = %blockL58i1_58
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL58i2_58

blockL58i2_58:                                    ; preds = %blockL58i1_62
  br label %blockL58i2_62

blockL58i2_62:                                    ; preds = %blockL58i2_58
  store volatile i8 2, ptr addrspace(1) %o, align 1
  br label %blockL58i3_58

blockL58i3_58:                                    ; preds = %blockL58i2_62
  br label %blockL58i3_62

blockL58i3_62:                                    ; preds = %blockL58i3_58
  store volatile i8 3, ptr addrspace(1) %o, align 1
  br label %blockL58i4_58

blockL58i4_58:                                    ; preds = %blockL58i3_62
  br label %blockL58i4_62

blockL58i4_62:                                    ; preds = %blockL58i4_58
  store volatile i8 4, ptr addrspace(1) %o, align 1
  br label %blockL58i5_58

blockL58i5_58:                                    ; preds = %blockL58i4_62
  br label %block122

block122:                                         ; preds = %blockL58i5_58
  ret void
}
