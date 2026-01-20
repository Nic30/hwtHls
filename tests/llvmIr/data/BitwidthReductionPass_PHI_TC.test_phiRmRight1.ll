define void @test_phiRmRight1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb3.streamSegSplit.1lane

bb3.streamSegSplit.1lane:                         ; preds = %bb3.backedge.1lane, %bb0
  %0 = load volatile i20, ptr addrspace(1) %i, align 4
  %1 = call i1 @hwtHls.bitRangeGet.i20.i6.i1.18(i20 %0, i6 18) #1
  %i_read1.r0.enable.0lane = call i1 @hwtHls.bitRangeGet.i20.i6.i1.16(i20 %0, i6 16) #1
  %2 = call i8 @hwtHls.bitRangeGet.i20.i6.i8.8(i20 %0, i6 8) #1
  %3 = call i8 @hwtHls.bitRangeGet.i20.i6.i8.0(i20 %0, i6 0) #1
  %4 = icmp eq i8 %3, 2
  %brmerge.not = and i1 %i_read1.r0.enable.0lane, %4
  %i_read1.r0.enable.0lane.not = xor i1 %i_read1.r0.enable.0lane, true
  %5 = call i9 @hwtHls.bitConcat.i8.i1(i8 %2, i1 %1) #1
  br i1 %brmerge.not, label %bb5.sink.split.1lane, label %irr.guard

bb3.backedge.0lane:                               ; preds = %irr.guard
  br i1 %i_read1.r0.enable.1lane, label %bb3.segmentEnCheckAfter.1lane, label %bb3.backedge.1lane

bb3.backedge.1lane:                               ; preds = %bb5.sink.split.1lane, %bb3.backedge.0lane
  br label %bb3.streamSegSplit.1lane

bb3.segmentEnCheckAfter.1lane:                    ; preds = %bb3.backedge.0lane
  br i1 %11, label %bb4.streamSegSplit.1lane, label %bb5.sink.split.1lane

bb4.streamSegSplit.1lane:                         ; preds = %bb3.segmentEnCheckAfter.1lane
  %6 = load volatile i20, ptr addrspace(1) %i, align 4
  %7 = call i1 @hwtHls.bitRangeGet.i20.i6.i1.18(i20 %6, i6 18) #1
  %8 = call i8 @hwtHls.bitRangeGet.i20.i6.i8.8(i20 %6, i6 8) #1
  %9 = call i8 @hwtHls.bitRangeGet.i20.i6.i8.0(i20 %6, i6 0) #1
  %ld.s19 = call i9 @hwtHls.bitConcat.i8.i1(i8 %8, i1 %7) #1
  br label %bb5.sink.split.0lane

bb5.sink.split.0lane:                             ; preds = %irr.guard, %bb4.streamSegSplit.1lane
  %i.1segment.01 = phi i9 [ %ld.s19, %bb4.streamSegSplit.1lane ], [ %ld.s1, %irr.guard ]
  %i_read_data.sink.0lane = phi i8 [ %9, %bb4.streamSegSplit.1lane ], [ %3, %irr.guard ]
  store volatile i8 %i_read_data.sink.0lane, ptr addrspace(2) %o, align 1
  br label %irr.guard

bb5.sink.split.1lane:                             ; preds = %bb3.segmentEnCheckAfter.1lane, %bb3.streamSegSplit.1lane
  %i_read_data.sink.1lane = phi i8 [ %i_read1.r0.data.1lane, %bb3.segmentEnCheckAfter.1lane ], [ %2, %bb3.streamSegSplit.1lane ]
  store volatile i8 %i_read_data.sink.1lane, ptr addrspace(2) %o, align 1
  br label %bb3.backedge.1lane

irr.guard:                                        ; preds = %bb5.sink.split.0lane, %bb3.streamSegSplit.1lane
  %i.1segment.1.moved2 = phi i9 [ %5, %bb3.streamSegSplit.1lane ], [ %i.1segment.01, %bb5.sink.split.0lane ]
  %Guard.bb3.backedge.0lane = phi i1 [ %i_read1.r0.enable.0lane.not, %bb3.streamSegSplit.1lane ], [ true, %bb5.sink.split.0lane ]
  %10 = call i8 @hwtHls.bitRangeGet.i9.i5.i8.0(i9 %i.1segment.1.moved2, i5 0) #1
  %i_read1.r0.enable.1lane = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %i.1segment.1.moved2, i5 8) #1
  %i_read1.r0.data.1lane = call i8 @hwtHls.bitRangeGet.i9.i5.i8.0(i9 %i.1segment.1.moved2, i5 0) #1
  %11 = icmp eq i8 %10, 2
  %ld.s1 = call i9 @hwtHls.bitConcat.i8.i1(i8 %2, i1 %1) #1
  br i1 %Guard.bb3.backedge.0lane, label %bb3.backedge.0lane, label %bb5.sink.split.0lane
}
