define void @HlsSlice.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_158, %block0
  %a_read = alloca i32, align 4, !hwtHls.tmp.alloca !4
  store i32 undef, ptr %a_read, align 4
  %a_read1 = load volatile i32, ptr addrspace(1) %a, align 4
  store i32 %a_read1, ptr %a_read, align 4
  %a_read2 = load i32, ptr %a_read, align 4
  %0 = call i16 @hwtHls.bitRangeGet.i32.i6.i16.0(i32 %a_read2, i6 0) #1
  store volatile i16 %0, ptr addrspace(2) %b, align 2
  br label %blockL14i0_158

blockL14i0_158:                                   ; preds = %blockL14i0_14
  br label %blockL14i0_14
}
