define void @InfLoopUnrollDissable.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %entry

entry:                                            ; preds = %bb0
  %i = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i, align 1
  store i8 0, ptr %i, align 1
  br label %loopHeader

loopHeader:                                       ; preds = %blockL108i0_262, %entry
  %i1 = load i8, ptr %i, align 1
  store volatile i8 %i1, ptr addrspace(1) %o, align 1
  %0 = add i8 %i1, 1
  store i8 %0, ptr %i, align 1
  br label %blockL108i0_262

blockL108i0_262:                                  ; preds = %loopHeader
  br label %loopHeader, !llvm.loop !3
}
