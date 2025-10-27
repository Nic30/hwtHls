define void @HlsPythonPreprocForInIf0.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %block128

block128:                                         ; preds = %block0
  br label %blockL150i0_150

blockL150i0_150:                                  ; preds = %block128
  br label %blockL150i0_154

blockL150i0_154:                                  ; preds = %blockL150i0_150
  store volatile i8 0, ptr addrspace(1) %o, align 1
  br label %blockL150i1_150

blockL150i1_150:                                  ; preds = %blockL150i0_154
  br label %blockL150i1_154

blockL150i1_154:                                  ; preds = %blockL150i1_150
  store volatile i8 1, ptr addrspace(1) %o, align 1
  br label %blockL150i2_150

blockL150i2_150:                                  ; preds = %blockL150i1_154
  br label %blockL150i2_154

blockL150i2_154:                                  ; preds = %blockL150i2_150
  store volatile i8 2, ptr addrspace(1) %o, align 1
  br label %blockL150i3_150

blockL150i3_150:                                  ; preds = %blockL150i2_154
  br label %block214

block214:                                         ; preds = %blockL150i3_150
  ret void
}
