define void @HlsAstExprTree3_example.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b, ptr addrspace(3) %c, ptr addrspace(4) %d, ptr addrspace(5) %f1, ptr addrspace(6) %f2, ptr addrspace(7) %f3, ptr addrspace(8) %w, ptr addrspace(9) %x, ptr addrspace(10) %y, ptr addrspace(11) %z) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL64i0_64

blockL64i0_64:                                    ; preds = %blockL64i0_724, %block0
  %a_read = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %a_read, align 4
  %b_read = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %b_read, align 4
  %c_read = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %c_read, align 4
  %d_read = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %d_read, align 4
  %a_read1 = load volatile i32, ptr addrspace(1) %a, align 4
  store i32 %a_read1, ptr %a_read, align 4
  %b_read1 = load volatile i32, ptr addrspace(2) %b, align 4
  store i32 %b_read1, ptr %b_read, align 4
  %c_read1 = load volatile i32, ptr addrspace(3) %c, align 4
  store i32 %c_read1, ptr %c_read, align 4
  %d_read1 = load volatile i32, ptr addrspace(4) %d, align 4
  store i32 %d_read1, ptr %d_read, align 4
  %x_read = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %x_read, align 4
  %y_read = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %y_read, align 4
  %z_read = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %z_read, align 4
  %w_read = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %w_read, align 4
  %x1 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %x1, align 4
  %x_read2 = load volatile i32, ptr addrspace(9) %x, align 4
  store i32 %x_read2, ptr %x_read, align 4
  %x_read3 = load i32, ptr %x_read, align 4
  store i32 %x_read3, ptr %x1, align 4
  %y1 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %y1, align 4
  %y_read2 = load volatile i32, ptr addrspace(10) %y, align 4
  store i32 %y_read2, ptr %y_read, align 4
  %y_read3 = load i32, ptr %y_read, align 4
  store i32 %y_read3, ptr %y1, align 4
  %z1 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %z1, align 4
  %z_read2 = load volatile i32, ptr addrspace(11) %z, align 4
  store i32 %z_read2, ptr %z_read, align 4
  %z_read3 = load i32, ptr %z_read, align 4
  store i32 %z_read3, ptr %z1, align 4
  %w1 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %w1, align 4
  %w_read2 = load volatile i32, ptr addrspace(8) %w, align 4
  store i32 %w_read2, ptr %w_read, align 4
  %w_read3 = load i32, ptr %w_read, align 4
  store i32 %w_read3, ptr %w1, align 4
  %a4 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %a4, align 4
  store i32 %a_read1, ptr %a4, align 4
  %b5 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %b5, align 4
  store i32 %b_read1, ptr %b5, align 4
  %c6 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %c6, align 4
  store i32 %c_read1, ptr %c6, align 4
  %d7 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %d7, align 4
  store i32 %d_read1, ptr %d7, align 4
  %f11 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %f11, align 4
  %0 = add i32 %a_read1, %b_read1
  %1 = add i32 %0, %c_read1
  %f18 = mul i32 %1, %d_read1
  store i32 %f18, ptr %f11, align 4
  %xy = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %xy, align 4
  %xy9 = add i32 %x_read3, %y_read3
  store i32 %xy9, ptr %xy, align 4
  %f21 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %f21, align 4
  %f210 = mul i32 %xy9, %z_read3
  store i32 %f210, ptr %f21, align 4
  %f31 = alloca i32, align 4, !hwtHls.tmp.alloca !13
  store i32 undef, ptr %f31, align 4
  %f311 = mul i32 %xy9, %w_read3
  store i32 %f311, ptr %f31, align 4
  store volatile i32 %f18, ptr addrspace(5) %f1, align 4
  store volatile i32 %f210, ptr addrspace(6) %f2, align 4
  store volatile i32 %f311, ptr addrspace(7) %f3, align 4
  br label %blockL64i0_724

blockL64i0_724:                                   ; preds = %blockL64i0_64
  br label %blockL64i0_64
}
