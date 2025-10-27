define void @InfLoopUnrollDissable.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %entry

entry:                                            ; preds = %bb0
  %i = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i, align 1
  store i8 0, ptr %i, align 1
  br label %loopHeader

loopHeader:                                       ; preds = %blockL122i0_286, %entry
  %i1 = load i8, ptr %i, align 1
  store volatile i8 %i1, ptr addrspace(1) %o, align 1
  %0 = add i8 %i1, 1
  store i8 %0, ptr %i, align 1
  br label %blockL122i0_286

blockL122i0_286:                                  ; preds = %loopHeader
  br label %loopHeader, !llvm.loop !3
}
