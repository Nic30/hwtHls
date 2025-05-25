define void @PhiShift0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %phi = phi i16 [ 0, %bb0 ], [ %newPhiVal, %bb1 ]
  %phiB0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %phi, i5 0) #1
  %phiB1 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %phi, i5 8) #1
  %i_read = load volatile i8, ptr addrspace(1) %i, align 1
  store volatile i8 %phiB1, ptr addrspace(2) %o, align 1
  %newPhiVal = call i16 @hwtHls.bitConcat.i8.i8(i8 %i_read, i8 %phiB0) #1
  br label %bb1
}
