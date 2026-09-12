define void @test_speculatePredecessor1(ptr addrspace(1) %o) {
bb0:
  br label %bb.loop0.head

bb.loop0.head:                                    ; preds = %bb.loop2.head, %bb0
  br label %bb.loop2.head

bb.loop2.head:                                    ; preds = %bb.loop2.head, %bb.loop0.head
  %i0 = phi i3 [ 0, %bb.loop0.head ], [ %i0.mux, %bb.loop2.head ]
  %i2 = phi i3 [ 0, %bb.loop0.head ], [ %.mux, %bb.loop2.head ]
  %i3 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i2, i3 0) #1
  %i1 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %i0, i3 0) #1
  %0 = call i8 @hwtHls.bitConcat.i2.i2.i4(i2 %i3, i2 %i1, i4 0) #1
  store volatile i8 %0, ptr addrspace(1) %o, align 1
  %1 = add i3 %i2, 1
  %hwrange.continue4.not1 = icmp eq i3 %i2, 3
  %2 = xor i1 %hwrange.continue4.not1, true
  %3 = add i3 %i0, 1
  %hwrange.continue.not.le.le2 = icmp eq i3 %i0, 3
  %hwrange.continue.not.le.le2.not = xor i1 %hwrange.continue.not.le.le2, true
  %brmerge = or i1 %2, %hwrange.continue.not.le.le2.not
  %i0.mux = select i1 %hwrange.continue4.not1, i3 %3, i3 %i0
  %.mux = select i1 %hwrange.continue4.not1, i3 0, i3 %1
  br i1 %brmerge, label %bb.loop2.head, label %bb.loop0.head
}
