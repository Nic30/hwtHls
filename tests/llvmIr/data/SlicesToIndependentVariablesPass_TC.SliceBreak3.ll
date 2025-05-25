define void @SliceBreak3.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i_read = alloca i32, align 4, !hwtHls.tmp.alloca !2
  store i32 undef, ptr %i_read, align 4
  %i1 = alloca i32, align 4, !hwtHls.tmp.alloca !2
  store i32 undef, ptr %i1, align 4
  %i_read2 = load volatile i32, ptr addrspace(1) %i, align 4
  store i32 %i_read2, ptr %i_read, align 4
  %i_read3 = load i32, ptr %i_read, align 4
  store i32 %i_read3, ptr %i1, align 4
  %x0 = alloca i32, align 4, !hwtHls.tmp.alloca !2
  store i32 undef, ptr %x0, align 4
  store i32 %i_read3, ptr %x0, align 4
  %x1 = alloca i32, align 4, !hwtHls.tmp.alloca !2
  store i32 undef, ptr %x1, align 4
  %0 = add i32 %i_read3, 1
  %1 = call i16 @hwtHls.bitRangeGet.i32.i6.i16.16(i32 %0, i6 16) #1
  %2 = call i16 @hwtHls.bitRangeGet.i32.i6.i16.0(i32 %0, i6 0) #1
  %3 = xor i16 %2, -1
  %4 = xor i16 %1, -1
  %5 = call i32 @hwtHls.bitConcat.i16.i16(i16 %3, i16 %4) #1
  %6 = xor i16 %2, -1
  %7 = xor i16 %1, -1
  store i32 %5, ptr %x1, align 4
  %x2 = alloca i32, align 4, !hwtHls.tmp.alloca !2
  store i32 undef, ptr %x2, align 4
  %8 = call i32 @hwtHls.bitConcat.i16.i16(i16 %6, i16 %7) #1
  store i32 %8, ptr %x2, align 4
  store volatile i32 %8, ptr addrspace(2) %o, align 4
  ret void
}
