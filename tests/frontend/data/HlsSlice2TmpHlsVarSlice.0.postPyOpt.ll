define void @HlsSlice2TmpHlsVarSlice.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_294, %block0
  %tmp = alloca i32, align 4, !hwtHls.tmp.alloca !2
  store i32 undef, ptr %tmp, align 4
  store i32 undef, ptr %tmp, align 4
  %tmp1 = call i48 @hwtHls.bitConcat.i16.i16.i16(i16 undef, i16 16, i16 undef) #1
  store i48 %tmp1, ptr %tmp, align 8
  %a_read = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %a_read, align 2
  %a_read1 = load volatile i16, ptr addrspace(1) %a, align 2
  store i16 %a_read1, ptr %a_read, align 2
  %a_read2 = load i16, ptr %a_read, align 2
  %tmp3 = load i32, ptr %tmp, align 4
  %0 = call i16 @hwtHls.bitRangeGet.i32.i6.i16.16(i32 %tmp3, i6 16) #1
  %tmp4 = call i32 @hwtHls.bitConcat.i16.i16(i16 %a_read2, i16 %0) #1
  store i32 %tmp4, ptr %tmp, align 4
  %tmp5 = load i32, ptr %tmp, align 4
  store volatile i32 %tmp5, ptr addrspace(2) %b, align 4
  br label %blockL14i0_294

blockL14i0_294:                                   ; preds = %blockL14i0_14
  br label %blockL14i0_14
}
