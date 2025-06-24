define void @Slice2.mainThread(ptr addrspace(1) %i0, ptr addrspace(2) %i1, ptr addrspace(3) %o) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  %i0_read = alloca i1, align 1, !hwtHls.tmp.alloca !5
  store i1 undef, ptr %i0_read, align 1
  %v3 = alloca i1, align 1, !hwtHls.tmp.alloca !5
  store i1 undef, ptr %v3, align 1
  %i0_read1 = load volatile i1, ptr addrspace(1) %i0, align 1
  store i1 %i0_read1, ptr %i0_read, align 1
  %i0_read2 = load i1, ptr %i0_read, align 1
  store i1 %i0_read2, ptr %v3, align 1
  %i1_read = alloca i5, align 1, !hwtHls.tmp.alloca !5
  store i5 undef, ptr %i1_read, align 1
  %v2 = alloca i5, align 1, !hwtHls.tmp.alloca !5
  store i5 undef, ptr %v2, align 1
  %i1_read1 = load volatile i5, ptr addrspace(2) %i1, align 1
  store i5 %i1_read1, ptr %i1_read, align 1
  %i1_read2 = load i5, ptr %i1_read, align 1
  %v95 = call i3 @hwtHls.bitRangeGet.i5.i4.i3.2(i5 %i1_read2, i4 2) #1
  %v43 = call i4 @hwtHls.bitRangeGet.i5.i4.i4.1(i5 %i1_read2, i4 1) #1
  store i5 %i1_read2, ptr %v2, align 1
  %v4 = alloca i4, align 1, !hwtHls.tmp.alloca !5
  store i4 undef, ptr %v4, align 1
  store i4 %v43, ptr %v4, align 1
  %v7 = alloca i5, align 1, !hwtHls.tmp.alloca !5
  store i5 undef, ptr %v7, align 1
  %0 = call i5 @hwtHls.bitConcat.i1.i4(i1 %i0_read2, i4 %v43) #1
  store i5 %0, ptr %v7, align 1
  %v9 = alloca i3, align 1, !hwtHls.tmp.alloca !5
  store i3 undef, ptr %v9, align 1
  store i3 %v95, ptr %v9, align 1
  %v13 = alloca i1, align 1, !hwtHls.tmp.alloca !5
  store i1 undef, ptr %v13, align 1
  store i1 false, ptr %v13, align 1
  %v12 = alloca i4, align 1, !hwtHls.tmp.alloca !5
  store i4 undef, ptr %v12, align 1
  %1 = call i4 @hwtHls.bitConcat.i1.i3(i1 false, i3 %v95) #1
  store i4 %1, ptr %v12, align 1
  %v15 = alloca i1, align 1, !hwtHls.tmp.alloca !5
  store i1 undef, ptr %v15, align 1
  store i1 %i0_read2, ptr %v15, align 1
  %v18 = alloca i5, align 1, !hwtHls.tmp.alloca !5
  store i5 undef, ptr %v18, align 1
  %2 = call i5 @hwtHls.bitConcat.i1.i1.i3(i1 %i0_read2, i1 false, i3 %v95) #1
  %3 = zext i1 %i0_read2 to i2
  store i5 %2, ptr %v18, align 1
  %v27 = alloca i2, align 1, !hwtHls.tmp.alloca !5
  store i2 undef, ptr %v27, align 1
  store i2 %3, ptr %v27, align 1
  store volatile i2 %3, ptr addrspace(3) %o, align 1
  ret void
}
