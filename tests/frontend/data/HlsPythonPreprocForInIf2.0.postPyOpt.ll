define void @HlsPythonPreprocForInIf2.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
bb0:
  br label %begin

begin:                                            ; preds = %bb0
  %cntr = alloca i8, align 1, !hwtHls.tmp.alloca !2
  store i8 undef, ptr %cntr, align 1
  store i8 0, ptr %cntr, align 1
  br label %blockL120i0_120

blockL120i0_120:                                  ; preds = %blockL120i0_468, %begin
  br label %if.true

if.true:                                          ; preds = %blockL120i0_120
  br label %blockL120i0_L200i0_200

blockL120i0_L200i0_200:                           ; preds = %if.true
  br label %for.head

for.head:                                         ; preds = %blockL120i0_L200i0_200
  %cntr1 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr1, ptr addrspace(1) %o, align 1
  %0 = icmp eq i8 %cntr1, 2
  br i1 %0, label %for.break, label %blockL120i0_L200i0_326

blockL120i0_L200i0_326:                           ; preds = %for.head
  br label %blockL120i0_L200i1_200

blockL120i0_L200i1_200:                           ; preds = %blockL120i0_L200i0_326
  br label %for.head2

for.break:                                        ; preds = %for.head2, %for.head
  br label %exit

for.head2:                                        ; preds = %blockL120i0_L200i1_200
  %cntr3 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr3, ptr addrspace(1) %o, align 1
  %1 = icmp eq i8 %cntr3, 2
  br i1 %1, label %for.break, label %blockL120i0_L200i1_326

blockL120i0_L200i1_326:                           ; preds = %for.head2
  br label %blockL120i0_L200i2_200

blockL120i0_L200i2_200:                           ; preds = %blockL120i0_L200i1_326
  br label %blockL120i0_356

blockL120i0_356:                                  ; preds = %blockL120i0_L200i2_200
  br label %exit

exit:                                             ; preds = %blockL120i0_356, %for.break
  %cntr5 = load i8, ptr %cntr, align 1
  store volatile i8 %cntr5, ptr addrspace(1) %o, align 1
  %2 = add i8 %cntr5, 1
  store i8 %2, ptr %cntr, align 1
  br label %blockL120i0_468

blockL120i0_468:                                  ; preds = %exit
  br label %blockL120i0_120
}
