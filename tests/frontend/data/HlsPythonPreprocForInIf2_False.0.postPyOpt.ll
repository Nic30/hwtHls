define void @HlsPythonPreprocForInIf2.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %begin

begin:                                            ; preds = %bb0
  %cntr = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %cntr, align 1
  store i8 0, ptr %cntr, align 1
  br label %blockL110i0_110

blockL110i0_110:                                  ; preds = %blockL110i0_428, %begin
  br label %exit

exit:                                             ; preds = %blockL110i0_110
  %cntr1 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr1, ptr addrspace(1) %o, align 1
  %0 = add i8 %cntr1, 1
  store i8 %0, ptr %cntr, align 1
  br label %blockL110i0_428

blockL110i0_428:                                  ; preds = %exit
  br label %blockL110i0_110
}
