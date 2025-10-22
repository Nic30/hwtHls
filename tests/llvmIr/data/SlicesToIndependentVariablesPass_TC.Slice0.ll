define void @Slice0.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i_read = alloca i16, align 2, !hwtHls.tmp.alloca !3
  store i16 undef, ptr %i_read, align 2
  %x = alloca i16, align 2, !hwtHls.tmp.alloca !3
  store i16 undef, ptr %x, align 2
  %i_read1 = load volatile i16, ptr addrspace(1) %i, align 2
  store i16 %i_read1, ptr %i_read, align 2
  %i_read2 = load i16, ptr %i_read, align 2
  store i16 %i_read2, ptr %x, align 2
  %0 = zext i16 %i_read2 to i32
  store volatile i32 %0, ptr addrspace(2) %o, align 4
  ret void
}
