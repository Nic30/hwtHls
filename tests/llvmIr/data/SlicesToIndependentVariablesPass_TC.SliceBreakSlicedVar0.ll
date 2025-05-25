define void @SliceBreakSlicedVar0.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %x = alloca i32, align 4, !hwtHls.tmp.alloca !2
  store i32 undef, ptr %x, align 4
  store i32 0, ptr %x, align 4
  store i32 1, ptr %x, align 4
  %x1 = load i32, ptr %x, align 4
  %0 = call i1 @hwtHls.bitRangeGet.i32.i6.i1.0(i32 %x1, i6 0) #1
  %1 = call i30 @hwtHls.bitRangeGet.i32.i6.i30.2(i32 %x1, i6 2) #1
  %2 = call i32 @hwtHls.bitConcat.i1.i1.i30(i1 %0, i1 true, i30 %1) #1
  store i32 %2, ptr %x, align 4
  %x3 = load i32, ptr %x, align 4
  store volatile i32 %x3, ptr addrspace(1) %o, align 4
  ret void
}
