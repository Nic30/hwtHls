define void @HlsPythonPreprocForInIf0.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %block26

block26:                                          ; preds = %block0
  br label %blockL48i0_48

blockL48i0_48:                                    ; preds = %block26
  br label %blockL48i0_52

blockL48i0_52:                                    ; preds = %blockL48i0_48
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL48i1_48

blockL48i1_48:                                    ; preds = %blockL48i0_52
  br label %blockL48i1_52

blockL48i1_52:                                    ; preds = %blockL48i1_48
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL48i2_48

blockL48i2_48:                                    ; preds = %blockL48i1_52
  br label %blockL48i2_52

blockL48i2_52:                                    ; preds = %blockL48i2_48
  store volatile i8 2, ptr addrspace(1) %o, align 1
  br label %blockL48i3_48

blockL48i3_48:                                    ; preds = %blockL48i2_52
  br label %blockL48i3_52

blockL48i3_52:                                    ; preds = %blockL48i3_48
  store volatile i8 3, ptr addrspace(1) %o, align 1
  br label %blockL48i4_48

blockL48i4_48:                                    ; preds = %blockL48i3_52
  br label %blockL48i4_52

blockL48i4_52:                                    ; preds = %blockL48i4_48
  store volatile i8 4, ptr addrspace(1) %o, align 1
  br label %blockL48i5_48

blockL48i5_48:                                    ; preds = %blockL48i4_52
  br label %block112

block112:                                         ; preds = %blockL48i5_48
  ret void
}
