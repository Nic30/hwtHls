define void @HlsConnectionFromPyIfElsePreproc.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %block6

block6:                                           ; preds = %block0
  %i_read = alloca i8, align 1, !hwtHls.tmp.alloca !4
  store i8 undef, ptr %i_read, align 1
  %v = alloca i8, align 1, !hwtHls.tmp.alloca !4
  store i8 undef, ptr %v, align 1
  %i_read1 = load volatile i8, ptr addrspace(1) %i, align 1
  store i8 %i_read1, ptr %i_read, align 1
  %i_read2 = load i8, ptr %i_read, align 1
  store i8 %i_read2, ptr %v, align 1
  %0 = icmp eq i8 %i_read2, 2
  br i1 %0, label %block114, label %block172

block114:                                         ; preds = %block6
  store volatile i8 3, ptr addrspace(2) %o, align 1
  ret void

block172:                                         ; preds = %block6
  store volatile i8 10, ptr addrspace(2) %o, align 1
  ret void
}
