define void @test_phiWithShiftIn(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %LCntr

LCntr:                                            ; preds = %LFinalWrite, %LCntr, %bb0
  %cntr.03 = phi i4 [ 7, %LFinalWrite ], [ %1, %LCntr ], [ 7, %bb0 ]
  %data.0.shiftPhi = phi i7 [ %4, %LFinalWrite ], [ %2, %LCntr ], [ undef, %bb0 ]
  %0 = call i6 @hwtHls.bitRangeGet.i7.i4.i6.1(i7 %data.0.shiftPhi, i4 1) #1
  %i_read1 = load volatile i1, ptr addrspace(1) %i, align 1
  %1 = add nsw i4 %cntr.03, -1
  %.not = icmp eq i4 %cntr.03, 0
  %2 = call i7 @hwtHls.bitConcat.i6.i1(i6 %0, i1 %i_read1) #1
  br i1 %.not, label %LFinalWrite, label %LCntr

LFinalWrite:                                      ; preds = %LCntr
  %3 = call i8 @hwtHls.bitConcat.i7.i1(i7 %data.0.shiftPhi, i1 %i_read1) #1
  store volatile i8 %3, ptr addrspace(2) %o, align 1
  %4 = call i7 @hwtHls.bitConcat.i6.i1(i6 %0, i1 %i_read1) #1
  br label %LCntr
}
