define void @HlsPythonPreprocForInIf1.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %begin

begin:                                            ; preds = %bb0
  %cntr = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %cntr, align 1
  store i8 0, ptr %cntr, align 1
  br label %if.true

if.true:                                          ; preds = %begin
  br label %blockL178i0_178

blockL178i0_178:                                  ; preds = %if.true
  br label %for.head

for.head:                                         ; preds = %blockL178i0_178
  %cntr1 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr1, ptr addrspace(1) %o, align 1
  %0 = icmp eq i8 %cntr1, 2
  br i1 %0, label %for.break, label %blockL178i0_304

blockL178i0_304:                                  ; preds = %for.head
  br label %blockL178i1_178

blockL178i1_178:                                  ; preds = %blockL178i0_304
  br label %for.head2

for.break:                                        ; preds = %for.head2, %for.head
  br label %exit

for.head2:                                        ; preds = %blockL178i1_178
  %cntr3 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr3, ptr addrspace(1) %o, align 1
  %1 = icmp eq i8 %cntr3, 2
  br i1 %1, label %for.break, label %blockL178i1_304

blockL178i1_304:                                  ; preds = %for.head2
  br label %blockL178i2_178

blockL178i2_178:                                  ; preds = %blockL178i1_304
  br label %block334

block334:                                         ; preds = %blockL178i2_178
  br label %exit

exit:                                             ; preds = %block334, %for.break
  %cntr5 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr5, ptr addrspace(1) %o, align 1
  ret void
}
