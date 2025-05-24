define void @HlsConnectionFromPyIf.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i_read = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %i_read, align 1
  %v = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %v, align 1
  %i_read1 = load volatile i8, ptr addrspace(1) %i, align 1
  store i8 %i_read1, ptr %i_read, align 1
  %i_read2 = load i8, ptr %i_read, align 1
  store i8 %i_read2, ptr %v, align 1
  %0 = icmp eq i8 %i_read2, 2
  br i1 %0, label %block110, label %block168

block110:                                         ; preds = %block0
  store volatile i8 3, ptr addrspace(2) %o, align 1
  ret void

block168:                                         ; preds = %block0
  ret void
}
