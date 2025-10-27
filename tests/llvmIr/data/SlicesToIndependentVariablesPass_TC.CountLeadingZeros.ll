define void @_BaseALU1HwModule.mainThread(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %block190

block190:                                         ; preds = %block0
  br label %blockL212i0_212

blockL212i0_212:                                  ; preds = %blockL212i0_376, %block190
  %data_in_read = alloca i4, align 1, !hwtHls.tmp.alloca !3
  store i4 undef, ptr %data_in_read, align 1
  %inp = alloca i4, align 1, !hwtHls.tmp.alloca !3
  store i4 undef, ptr %inp, align 1
  %data_in_read1 = load volatile i4, ptr addrspace(1) %data_in, align 1
  store i4 %data_in_read1, ptr %data_in_read, align 1
  %data_in_read2 = load i4, ptr %data_in_read, align 1
  store i4 %data_in_read2, ptr %inp, align 1
  br label %"blockL212i0_(CountLeadingZeros.aluFn, 292)_0"

"blockL212i0_(CountLeadingZeros.aluFn, 292)_0":   ; preds = %blockL212i0_212
  br label %blockL212i0_212_afterCall

blockL212i0_212_afterCall:                        ; preds = %"blockL212i0_(CountLeadingZeros.aluFn, 292)_0"
  %resTmp = alloca i3, align 1, !hwtHls.tmp.alloca !3
  store i3 undef, ptr %resTmp, align 1
  %inp3 = load i4, ptr %inp, align 1
  %0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %inp3, i3 3) #1
  %1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %inp3, i3 1) #1
  %2 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4 %inp3, i3 2) #1
  %3 = icmp eq i4 %inp3, 0
  %4 = icmp eq i2 %2, 0
  %5 = select i1 %4, i1 %1, i1 %0
  %6 = xor i1 %5, true
  %7 = call i2 @hwtHls.bitConcat.i1.i1(i1 %6, i1 %4) #1
  %resTmp41 = select i1 %3, i2 0, i2 %7
  %resTmp42 = select i1 %3, i1 true, i1 false
  %8 = call i3 @hwtHls.bitConcat.i2.i1(i2 %resTmp41, i1 %resTmp42) #1
  store i3 %8, ptr %resTmp, align 1
  store volatile i3 %8, ptr addrspace(2) %data_out, align 1
  br label %blockL212i0_376

blockL212i0_376:                                  ; preds = %blockL212i0_212_afterCall
  br label %blockL212i0_212
}
