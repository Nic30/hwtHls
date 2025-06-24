define void @HlsSlice2TmpHlsVarConcat.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_224, %block0
  %a_read = alloca i16, align 2, !hwtHls.tmp.alloca !4
  store i16 undef, ptr %a_read, align 2
  %tmp = alloca i32, align 4, !hwtHls.tmp.alloca !4
  store i32 undef, ptr %tmp, align 4
  %a_read1 = load volatile i16, ptr addrspace(1) %a, align 2
  store i16 %a_read1, ptr %a_read, align 2
  %a_read2 = load i16, ptr %a_read, align 2
  %tmp3 = call i32 @hwtHls.bitConcat.i16.i16(i16 %a_read2, i16 16) #1
  store i32 %tmp3, ptr %tmp, align 4
  store volatile i32 %tmp3, ptr addrspace(2) %b, align 4
  br label %blockL14i0_224

blockL14i0_224:                                   ; preds = %blockL14i0_14
  br label %blockL14i0_14
}
