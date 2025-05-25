define void @LoopCondBitSet(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %.phiConc33 = phi i4 [ -8, %bb0 ], [ %10, %bb1 ]
  %.phiConc = phi i4 [ 0, %bb0 ], [ %11, %bb1 ]
  %0 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.1(i4 %.phiConc33, i3 1) #1
  %1 = call i3 @hwtHls.bitRangeGet.i4.i3.i3.1(i4 %.phiConc33, i3 1) #1
  %2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %.phiConc33, i3 3) #1
  %"i0(i_read)" = load volatile i1, ptr addrspace(1) %i, align 1
  %.opConc = select i1 %"i0(i_read)", i4 %.phiConc33, i4 0
  %.opConc34 = or i4 %.phiConc, %.opConc
  %3 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.0(i4 %.opConc34, i3 0) #1
  %4 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4 %.opConc34, i3 2) #1
  store volatile i4 %.opConc34, ptr addrspace(2) %o, align 1
  %"9.not32" = icmp ne i3 %1, 0
  %5 = select i1 %"9.not32", i2 %4, i2 0
  %".10(qMask)5" = and i1 %2, %"9.not32"
  %6 = call i4 @hwtHls.bitConcat.i2.i2(i2 %3, i2 %0) #1
  %7 = select i1 %"9.not32", i4 %6, i4 0
  %8 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.0(i4 %7, i3 0) #1
  %9 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4 %7, i3 2) #1
  %"9.not" = icmp eq i3 %1, 0
  %10 = call i4 @hwtHls.bitConcat.i2.i1.i1(i2 %9, i1 %".10(qMask)5", i1 %"9.not") #1
  %11 = call i4 @hwtHls.bitConcat.i2.i2(i2 %8, i2 %5) #1
  br label %bb1
}
