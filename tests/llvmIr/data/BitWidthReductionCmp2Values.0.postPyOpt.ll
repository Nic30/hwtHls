define void @"BitWidthReductionCmp2Values.hwImpl.<locals>.mainThread"(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %entry

entry:                                            ; preds = %bb0
  br label %loopHeader

loopHeader:                                       ; preds = %blockL80i0_556, %entry
  %i_read = alloca i16, align 2, !hwtHls.tmp.alloca !3
  store i16 undef, ptr %i_read, align 2
  %i1 = alloca i16, align 2, !hwtHls.tmp.alloca !3
  store i16 undef, ptr %i1, align 2
  %i_read2 = load volatile i16, ptr addrspace(1) %i, align 2
  store i16 %i_read2, ptr %i_read, align 2
  %i_read3 = load i16, ptr %i_read, align 2
  store i16 %i_read3, ptr %i1, align 2
  %0 = icmp eq i16 %i_read3, 10
  br i1 %0, label %case10, label %blockL80i0_300

case10:                                           ; preds = %loopHeader
  store volatile i16 20, ptr addrspace(2) %o, align 2
  br label %blockL80i0_502

blockL80i0_502:                                   ; preds = %caseElse, %case11, %case10
  br label %blockL80i0_556

blockL80i0_556:                                   ; preds = %blockL80i0_502
  br label %loopHeader

blockL80i0_300:                                   ; preds = %loopHeader
  %i2 = load i16, ptr %i1, align 2
  %1 = icmp eq i16 %i2, 11
  br i1 %1, label %case11, label %caseElse

case11:                                           ; preds = %blockL80i0_300
  store volatile i16 25, ptr addrspace(2) %o, align 2
  br label %blockL80i0_502

caseElse:                                         ; preds = %blockL80i0_300
  store volatile i16 26, ptr addrspace(2) %o, align 2
  br label %blockL80i0_502
}
