define void @SliceBreakSlicedVar2.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %x = alloca i32, align 4, !hwtHls.tmp.alloca !2
  store i32 undef, ptr %x, align 4
  store i32 0, ptr %x, align 4
  store i32 32, ptr %x, align 4
  %x1 = load i32, ptr %x, align 4
  store volatile i32 %x1, ptr addrspace(1) %o, align 4
  ret void
}
