define void @phiRmLeftRight0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb.latch, %bb1, %bb0
  %r0 = load volatile i28, ptr addrspace(1) %i, align 4
  %0 = call i16 @hwtHls.bitRangeGet.i28.i6.i16.0(i28 %r0, i6 0) #2
  switch i16 %0, label %bb1 [
    i16 2, label %bb.off2
    i16 4, label %bb.off4
  ]

bb.off2:                                          ; preds = %bb1
  %1 = load volatile i28, ptr addrspace(1) %i, align 4
  %r.off2 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.26(i28 %1, i6 26) #2
  br label %bb.latch

bb.off4:                                          ; preds = %bb1
  %2 = load volatile i28, ptr addrspace(1) %i, align 4
  %r.off4 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.26(i28 %2, i6 26) #2
  br label %bb.latch

bb.latch:                                         ; preds = %bb.off4, %bb.off2
  %r.off.phi1 = phi i2 [ %r.off2, %bb.off2 ], [ %r.off4, %bb.off4 ]
  %3 = icmp sgt i2 %r.off.phi1, -1
  call void @llvm.assume(i1 %3)
  store volatile i32 3, ptr addrspace(2) %o, align 4
  br label %bb1
}
