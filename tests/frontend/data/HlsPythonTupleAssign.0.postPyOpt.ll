define void @HlsPythonTupleAssign.mainThread(ptr addrspace(1) %o0, ptr addrspace(2) %o1) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i0 = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i0, align 1
  store i8 0, ptr %i0, align 1
  %i1 = alloca i8, align 1, !hwtHls.tmp.alloca !3
  store i8 undef, ptr %i1, align 1
  store i8 1, ptr %i1, align 1
  br label %blockL112i0_112

blockL112i0_112:                                  ; preds = %blockL112i0_284, %block0
  %i01 = load i8, ptr %i0, align 1
  store volatile i8 %i01, ptr addrspace(1) %o0, align 1
  %i11 = load i8, ptr %i1, align 1
  store volatile i8 %i11, ptr addrspace(2) %o1, align 1
  store i8 %i11, ptr %i0, align 1
  store i8 %i01, ptr %i1, align 1
  br label %blockL112i0_284

blockL112i0_284:                                  ; preds = %blockL112i0_112
  br label %blockL112i0_112
}
