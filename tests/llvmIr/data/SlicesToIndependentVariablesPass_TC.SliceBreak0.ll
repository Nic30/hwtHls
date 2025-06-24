define void @SliceBreak0.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i_read = alloca i32, align 4, !hwtHls.tmp.alloca !4
  store i32 undef, ptr %i_read, align 4
  %i1 = alloca i32, align 4, !hwtHls.tmp.alloca !4
  store i32 undef, ptr %i1, align 4
  %i_read2 = load volatile i32, ptr addrspace(1) %i, align 4
  store i32 %i_read2, ptr %i_read, align 4
  %i_read3 = load i32, ptr %i_read, align 4
  store i32 %i_read3, ptr %i1, align 4
  %x = alloca i32, align 4, !hwtHls.tmp.alloca !4
  store i32 undef, ptr %x, align 4
  store i32 %i_read3, ptr %x, align 4
  store volatile i32 %i_read3, ptr addrspace(2) %o, align 4
  ret void
}
