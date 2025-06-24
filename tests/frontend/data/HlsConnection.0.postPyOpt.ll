define void @HlsConnection.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_152, %block0
  %a_read = alloca i32, align 4, !hwtHls.tmp.alloca !4
  store i32 undef, ptr %a_read, align 4
  %a_read1 = load volatile i32, ptr addrspace(1) %a, align 4
  store i32 %a_read1, ptr %a_read, align 4
  %a_read2 = load i32, ptr %a_read, align 4
  store volatile i32 %a_read2, ptr addrspace(2) %b, align 4
  br label %blockL14i0_152

blockL14i0_152:                                   ; preds = %blockL14i0_14
  br label %blockL14i0_14
}
