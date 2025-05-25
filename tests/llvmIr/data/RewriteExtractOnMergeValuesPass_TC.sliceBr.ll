define void @sliceBr(ptr addrspace(1) %dataIn) {
bb.0:
  %0 = load volatile i19, ptr addrspace(1) %dataIn, align 4
  %1 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %0, i6 17) #1
  %2 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %0, i6 18) #1
  %3 = xor i1 %1, true
  %4 = and i1 %2, %3
  br i1 %4, label %bb.1, label %bb.2

bb.1:                                             ; preds = %bb.0
  ret void

bb.2:                                             ; preds = %bb.0
  ret void
}
