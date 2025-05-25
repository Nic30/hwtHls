define void @phiShift(ptr addrspace(1) %i, ptr addrspace(2) %o) {
BB0:
  br label %BB1

BB1:                                              ; preds = %BB2, %BB0
  %i0 = load volatile i4, ptr addrspace(1) %i, align 1
  br label %BB2

BB2:                                              ; preds = %BB2, %BB1
  %.shiftPhi = phi i4 [ %i0, %BB1 ], [ %2, %BB2 ]
  %0 = call i3 @hwtHls.bitRangeGet.i4.i3.i3.1(i4 %.shiftPhi, i3 1) #1
  %1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %.shiftPhi, i3 0) #1
  store volatile i4 -5, ptr addrspace(2) %o, align 1
  %2 = zext i3 %0 to i4
  br i1 %1, label %BB2, label %BB1
}
