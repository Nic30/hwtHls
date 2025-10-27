define void @ExampleCntrArray.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %o_addr) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL54i0_54

blockL54i0_54:                                    ; preds = %block0
  br label %blockL54i0_58

blockL54i0_58:                                    ; preds = %blockL54i0_54
  %v0 = alloca i16, align 2, !hwtHls.tmp.alloca !4
  store i16 undef, ptr %v0, align 2
  br label %blockL54i1_54

blockL54i1_54:                                    ; preds = %blockL54i0_58
  br label %blockL54i1_58

blockL54i1_58:                                    ; preds = %blockL54i1_54
  %v1 = alloca i16, align 2, !hwtHls.tmp.alloca !4
  store i16 undef, ptr %v1, align 2
  br label %blockL54i2_54

blockL54i2_54:                                    ; preds = %blockL54i1_58
  br label %blockL54i2_58

blockL54i2_58:                                    ; preds = %blockL54i2_54
  %v2 = alloca i16, align 2, !hwtHls.tmp.alloca !4
  store i16 undef, ptr %v2, align 2
  br label %blockL54i3_54

blockL54i3_54:                                    ; preds = %blockL54i2_58
  br label %blockL54i3_58

blockL54i3_58:                                    ; preds = %blockL54i3_54
  %v3 = alloca i16, align 2, !hwtHls.tmp.alloca !4
  store i16 undef, ptr %v3, align 2
  br label %blockL54i4_54

blockL54i4_54:                                    ; preds = %blockL54i3_58
  br label %block146

block146:                                         ; preds = %blockL54i4_54
  br label %blockL158i0_158

blockL158i0_158:                                  ; preds = %block146
  br label %blockL158i0_162

blockL158i0_162:                                  ; preds = %blockL158i0_158
  store i16 0, ptr %v0, align 2
  br label %blockL158i1_158

blockL158i1_158:                                  ; preds = %blockL158i0_162
  br label %blockL158i1_162

blockL158i1_162:                                  ; preds = %blockL158i1_158
  store i16 0, ptr %v1, align 2
  br label %blockL158i2_158

blockL158i2_158:                                  ; preds = %blockL158i1_162
  br label %blockL158i2_162

blockL158i2_162:                                  ; preds = %blockL158i2_158
  store i16 0, ptr %v2, align 2
  br label %blockL158i3_158

blockL158i3_158:                                  ; preds = %blockL158i2_162
  br label %blockL158i3_162

blockL158i3_162:                                  ; preds = %blockL158i3_158
  store i16 0, ptr %v3, align 2
  br label %blockL158i4_158

blockL158i4_158:                                  ; preds = %blockL158i3_162
  br label %block184

block184:                                         ; preds = %blockL158i4_158
  br label %blockL210i0_210

blockL210i0_210:                                  ; preds = %blockL210i0_460, %block184
  %o_addr_read = alloca i2, align 1, !hwtHls.tmp.alloca !4
  store i2 undef, ptr %o_addr_read, align 1
  %o1 = alloca i16, align 2, !hwtHls.tmp.alloca !4
  store i16 undef, ptr %o1, align 2
  %o_addr_read1 = load volatile i2, ptr addrspace(3) %o_addr, align 1
  store i2 %o_addr_read1, ptr %o_addr_read, align 1
  %o_addr_read2 = load i2, ptr %o_addr_read, align 1
  %0 = icmp eq i2 %o_addr_read2, 0
  %v03 = load i16, ptr %v0, align 2
  %1 = icmp eq i2 %o_addr_read2, 1
  %v14 = load i16, ptr %v1, align 2
  %2 = icmp eq i2 %o_addr_read2, -2
  %v25 = load i16, ptr %v2, align 2
  %v36 = load i16, ptr %v3, align 2
  %3 = select i1 %2, i16 %v25, i16 %v36
  %4 = select i1 %1, i16 %v14, i16 %3
  %o7 = select i1 %0, i16 %v03, i16 %4
  store i16 %o7, ptr %o1, align 2
  %i_read = alloca i2, align 1, !hwtHls.tmp.alloca !4
  store i2 undef, ptr %i_read, align 1
  store volatile i16 %o7, ptr addrspace(2) %o, align 2
  %i_read1 = load volatile i2, ptr addrspace(1) %i, align 1
  store i2 %i_read1, ptr %i_read, align 1
  %i_read2 = load i2, ptr %i_read, align 1
  switch i2 %i_read2, label %blockL210i0_210_434_setSwEnd [
    i2 0, label %blockL210i0_210_434_c0
    i2 1, label %blockL210i0_210_434_c1
    i2 -2, label %blockL210i0_210_434_c2
    i2 -1, label %blockL210i0_210_434_c3
  ]

blockL210i0_210_434_setSwEnd:                     ; preds = %blockL210i0_210_434_c3, %blockL210i0_210_434_c2, %blockL210i0_210_434_c1, %blockL210i0_210_434_c0, %blockL210i0_210
  br label %blockL210i0_460

blockL210i0_210_434_c0:                           ; preds = %blockL210i0_210
  %i_read3 = load i2, ptr %i_read, align 1
  %5 = icmp eq i2 %i_read3, 0
  %v04 = load i16, ptr %v0, align 2
  %6 = icmp eq i2 %i_read3, 1
  %v15 = load i16, ptr %v1, align 2
  %7 = icmp eq i2 %i_read3, -2
  %v26 = load i16, ptr %v2, align 2
  %v37 = load i16, ptr %v3, align 2
  %8 = select i1 %7, i16 %v26, i16 %v37
  %9 = select i1 %6, i16 %v15, i16 %8
  %10 = select i1 %5, i16 %v04, i16 %9
  %11 = add i16 %10, 1
  store i16 %11, ptr %v0, align 2
  br label %blockL210i0_210_434_setSwEnd

blockL210i0_210_434_c1:                           ; preds = %blockL210i0_210
  %i_read8 = load i2, ptr %i_read, align 1
  %12 = icmp eq i2 %i_read8, 0
  %v09 = load i16, ptr %v0, align 2
  %13 = icmp eq i2 %i_read8, 1
  %v110 = load i16, ptr %v1, align 2
  %14 = icmp eq i2 %i_read8, -2
  %v211 = load i16, ptr %v2, align 2
  %v312 = load i16, ptr %v3, align 2
  %15 = select i1 %14, i16 %v211, i16 %v312
  %16 = select i1 %13, i16 %v110, i16 %15
  %17 = select i1 %12, i16 %v09, i16 %16
  %18 = add i16 %17, 1
  store i16 %18, ptr %v1, align 2
  br label %blockL210i0_210_434_setSwEnd

blockL210i0_210_434_c2:                           ; preds = %blockL210i0_210
  %i_read13 = load i2, ptr %i_read, align 1
  %19 = icmp eq i2 %i_read13, 0
  %v014 = load i16, ptr %v0, align 2
  %20 = icmp eq i2 %i_read13, 1
  %v115 = load i16, ptr %v1, align 2
  %21 = icmp eq i2 %i_read13, -2
  %v216 = load i16, ptr %v2, align 2
  %v317 = load i16, ptr %v3, align 2
  %22 = select i1 %21, i16 %v216, i16 %v317
  %23 = select i1 %20, i16 %v115, i16 %22
  %24 = select i1 %19, i16 %v014, i16 %23
  %25 = add i16 %24, 1
  store i16 %25, ptr %v2, align 2
  br label %blockL210i0_210_434_setSwEnd

blockL210i0_210_434_c3:                           ; preds = %blockL210i0_210
  %i_read18 = load i2, ptr %i_read, align 1
  %26 = icmp eq i2 %i_read18, 0
  %v019 = load i16, ptr %v0, align 2
  %27 = icmp eq i2 %i_read18, 1
  %v120 = load i16, ptr %v1, align 2
  %28 = icmp eq i2 %i_read18, -2
  %v221 = load i16, ptr %v2, align 2
  %v322 = load i16, ptr %v3, align 2
  %29 = select i1 %28, i16 %v221, i16 %v322
  %30 = select i1 %27, i16 %v120, i16 %29
  %31 = select i1 %26, i16 %v019, i16 %30
  %32 = add i16 %31, 1
  store i16 %32, ptr %v3, align 2
  br label %blockL210i0_210_434_setSwEnd

blockL210i0_460:                                  ; preds = %blockL210i0_210_434_setSwEnd
  br label %blockL210i0_210
}
