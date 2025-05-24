define void @HlsPythonPreprocForInIf1.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
bb0:
  br label %begin

begin:                                            ; preds = %bb0
  %cntr = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %cntr, align 1
  store i8 0, ptr %cntr, align 1
  br label %if.true

if.true:                                          ; preds = %begin
  br label %blockL168i0_168

blockL168i0_168:                                  ; preds = %if.true
  br label %for.head

for.head:                                         ; preds = %blockL168i0_168
  %cntr1 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr1, ptr addrspace(1) %o, align 1
  %0 = icmp eq i8 %cntr1, 2
  br i1 %0, label %for.break, label %blockL168i0_286

blockL168i0_286:                                  ; preds = %for.head
  br label %blockL168i1_168

blockL168i1_168:                                  ; preds = %blockL168i0_286
  br label %for.head2

for.break:                                        ; preds = %for.head2, %for.head
  br label %exit

for.head2:                                        ; preds = %blockL168i1_168
  %cntr3 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr3, ptr addrspace(1) %o, align 1
  %1 = icmp eq i8 %cntr3, 2
  br i1 %1, label %for.break, label %blockL168i1_286

blockL168i1_286:                                  ; preds = %for.head2
  br label %blockL168i2_168

blockL168i2_168:                                  ; preds = %blockL168i1_286
  br label %block314

block314:                                         ; preds = %blockL168i2_168
  br label %exit

exit:                                             ; preds = %block314, %for.break
  %cntr5 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr5, ptr addrspace(1) %o, align 1
  ret void
}
