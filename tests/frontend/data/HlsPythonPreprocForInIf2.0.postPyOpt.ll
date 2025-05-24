define void @HlsPythonPreprocForInIf2.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %begin

begin:                                            ; preds = %bb0
  %cntr = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %cntr, align 1
  store i8 0, ptr %cntr, align 1
  br label %blockL110i0_110

blockL110i0_110:                                  ; preds = %blockL110i0_428, %begin
  br label %if.true

if.true:                                          ; preds = %blockL110i0_110
  br label %blockL110i0_L180i0_180

blockL110i0_L180i0_180:                           ; preds = %if.true
  br label %for.head

for.head:                                         ; preds = %blockL110i0_L180i0_180
  %cntr1 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr1, ptr addrspace(1) %o, align 1
  %0 = icmp eq i8 %cntr1, 2
  br i1 %0, label %for.break, label %blockL110i0_L180i0_298

blockL110i0_L180i0_298:                           ; preds = %for.head
  br label %blockL110i0_L180i1_180

blockL110i0_L180i1_180:                           ; preds = %blockL110i0_L180i0_298
  br label %for.head2

for.break:                                        ; preds = %for.head2, %for.head
  br label %exit

for.head2:                                        ; preds = %blockL110i0_L180i1_180
  %cntr3 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr3, ptr addrspace(1) %o, align 1
  %1 = icmp eq i8 %cntr3, 2
  br i1 %1, label %for.break, label %blockL110i0_L180i1_298

blockL110i0_L180i1_298:                           ; preds = %for.head2
  br label %blockL110i0_L180i2_180

blockL110i0_L180i2_180:                           ; preds = %blockL110i0_L180i1_298
  br label %blockL110i0_326

blockL110i0_326:                                  ; preds = %blockL110i0_L180i2_180
  br label %exit

exit:                                             ; preds = %blockL110i0_326, %for.break
  %cntr5 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr5, ptr addrspace(1) %o, align 1
  %2 = add i8 %cntr5, 1
  store i8 %2, ptr %cntr, align 1
  br label %blockL110i0_428

blockL110i0_428:                                  ; preds = %exit
  br label %blockL110i0_110
}
