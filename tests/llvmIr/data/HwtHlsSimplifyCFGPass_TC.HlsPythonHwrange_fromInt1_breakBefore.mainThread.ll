define void @HlsPythonHwrange_fromInt1_breakBefore.mainThread(ptr addrspace(1) %o) {
bb0:
  br label %bb.loop0.head

bb.loop0.head:                                    ; preds = %bb.loop0.latch, %bb0
  %i0 = phi i4 [ 0, %bb0 ], [ %i0.be, %bb.loop0.latch ]
  %0 = icmp eq i4 %i0, 4
  %1 = zext i4 %i0 to i8
  br i1 %0, label %bb2, label %bb1

bb1:                                              ; preds = %bb.loop0.head
  store volatile i8 %1, ptr addrspace(1) %o, align 1
  %2 = add nuw i4 %i0, 1
  %hwrange.continue1 = icmp ne i4 %i0, 7
  br i1 %hwrange.continue1, label %bb.loop0.latch, label %bb2

bb2:                                              ; preds = %bb1, %bb.loop0.head
  br label %bb.loop0.latch

bb.loop0.latch:                                   ; preds = %bb2, %bb1
  %i0.be = phi i4 [ 0, %bb2 ], [ %2, %bb1 ]
  br label %bb.loop0.head
}
