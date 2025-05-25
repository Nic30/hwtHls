define void @PhiWithConstValues(ptr addrspace(1) %o0, ptr addrspace(2) %o1) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %shiftPhi1 = phi i2 [ -2, %bb0 ], [ %4, %bb1 ]
  %0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %shiftPhi1, i2 1) #1
  %1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %shiftPhi1, i2 0) #1
  %2 = zext i1 %1 to i8
  store volatile i8 %2, ptr addrspace(1) %o0, align 1
  %3 = zext i1 %0 to i8
  store volatile i8 %3, ptr addrspace(2) %o1, align 1
  %4 = call i2 @hwtHls.bitConcat.i1.i1(i1 %0, i1 %1) #1
  br label %bb1
}
