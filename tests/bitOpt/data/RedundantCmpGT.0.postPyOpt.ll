define void @RedundantCmpGT.mainThread(ptr addrspace(1) %i0, ptr addrspace(2) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_174, %block0
  %i0_read = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i0_read, align 1
  %i01 = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i01, align 1
  %i0_read2 = load volatile i8, ptr addrspace(1) %i0, align 1
  store i8 %i0_read2, ptr %i0_read, align 1
  %i0_read3 = load i8, ptr %i0_read, align 1
  store i8 %i0_read3, ptr %i01, align 1
  %0 = icmp ugt i8 %i0_read3, 1
  %1 = icmp ugt i8 %i0_read3, 2
  %2 = or i1 %0, %1
  store volatile i1 %2, ptr addrspace(2) %o, align 1
  br label %blockL14i0_174

blockL14i0_174:                                   ; preds = %blockL14i0_14
  br label %blockL14i0_14
}
