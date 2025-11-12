define void @StreamSegmentLoopUnrollPass_TC.headerPop(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb1.streamSegSplit.1lane

bb1.streamSegSplit.0lane:                         ; preds = %bb1.backedge.0lane
  br label %bb1.1lane

bb1.streamSegSplit.1lane:                         ; preds = %bb1.backedge.1lane, %bb0
  br label %bb1.0lane

bb1.0lane:                                        ; preds = %bb1.streamSegSplit.1lane
  %0 = load volatile i268, ptr addrspace(1) %rx, align 64
  %1 = call i6 @hwtHls.bitRangeGet.i268.i10.i6.262(i268 %0, i10 262) #1
  %2 = call i128 @hwtHls.bitRangeGet.i268.i10.i128.128(i268 %0, i10 128) #1
  %3 = call i128 @hwtHls.bitRangeGet.i268.i10.i128.0(i268 %0, i10 0) #1
  %4 = call i6 @hwtHls.bitRangeGet.i268.i10.i6.256(i268 %0, i10 256) #1
  %ld.s0 = call i134 @hwtHls.bitConcat.i128.i6(i128 %3, i6 %4) #1
  %ld.s1 = call i134 @hwtHls.bitConcat.i128.i6(i128 %2, i6 %1) #1
  %r0.eof.0lane = icmp ne i134 %ld.s0, 0
  br i1 %r0.eof.0lane, label %bb1.backedge.0lane, label %bb1.segmentEnCheck.after.streamSegSplit.0lane

bb1.1lane:                                        ; preds = %bb1.streamSegSplit.0lane
  %r0.eof.1lane = icmp ne i134 %rx.1segment.0, 0
  br i1 %r0.eof.1lane, label %bb1.backedge.1lane, label %bb1.segmentEnCheck.after.streamSegSplit.1lane

bb1.segmentEnCheck.after.streamSegSplit.0lane:    ; preds = %bb1.0lane
  br label %bb1.segmentEnCheck.after.1lane

bb1.segmentEnCheck.after.streamSegSplit.1lane:    ; preds = %bb1.1lane
  br label %bb1.segmentEnCheck.after.0lane

bb1.segmentEnCheck.after.0lane:                   ; preds = %bb1.segmentEnCheck.after.streamSegSplit.1lane
  %5 = load volatile i268, ptr addrspace(1) %rx, align 64
  %6 = call i6 @hwtHls.bitRangeGet.i268.i10.i6.262(i268 %5, i10 262) #1
  %7 = call i128 @hwtHls.bitRangeGet.i268.i10.i128.128(i268 %5, i10 128) #1
  %8 = call i128 @hwtHls.bitRangeGet.i268.i10.i128.0(i268 %5, i10 0) #1
  %9 = call i6 @hwtHls.bitRangeGet.i268.i10.i6.256(i268 %5, i10 256) #1
  %ld.s01 = call i134 @hwtHls.bitConcat.i128.i6(i128 %8, i6 %9) #1
  %ld.s12 = call i134 @hwtHls.bitConcat.i128.i6(i128 %7, i6 %6) #1
  br label %bb.forwardUntilEoF.streamSegSplit.0lane

bb1.segmentEnCheck.after.1lane:                   ; preds = %bb1.segmentEnCheck.after.streamSegSplit.0lane
  br label %bb.forwardUntilEoF.streamSegSplit.1lane

bb.forwardUntilEoF.streamSegSplit.0lane:          ; preds = %bb.forwardUntilEoF.0lane, %bb1.segmentEnCheck.after.0lane
  %rx.1segment.1 = phi i134 [ %ld.s12, %bb1.segmentEnCheck.after.0lane ], [ %ld.s14, %bb.forwardUntilEoF.0lane ]
  %r.phi.0lane = phi i134 [ %ld.s01, %bb1.segmentEnCheck.after.0lane ], [ %ld.s03, %bb.forwardUntilEoF.0lane ]
  br label %bb.forwardUntilEoF.1lane

bb.forwardUntilEoF.streamSegSplit.1lane:          ; preds = %bb.forwardUntilEoF.1lane, %bb1.segmentEnCheck.after.1lane
  %r.phi.1lane = phi i134 [ %ld.s1, %bb1.segmentEnCheck.after.1lane ], [ %rx.1segment.1, %bb.forwardUntilEoF.1lane ]
  br label %bb.forwardUntilEoF.0lane

bb.forwardUntilEoF.0lane:                         ; preds = %bb.forwardUntilEoF.streamSegSplit.1lane
  %10 = load volatile i268, ptr addrspace(1) %rx, align 64
  %11 = call i6 @hwtHls.bitRangeGet.i268.i10.i6.262(i268 %10, i10 262) #1
  %12 = call i128 @hwtHls.bitRangeGet.i268.i10.i128.128(i268 %10, i10 128) #1
  %13 = call i128 @hwtHls.bitRangeGet.i268.i10.i128.0(i268 %10, i10 0) #1
  %14 = call i6 @hwtHls.bitRangeGet.i268.i10.i6.256(i268 %10, i10 256) #1
  %ld.s03 = call i134 @hwtHls.bitConcat.i128.i6(i128 %13, i6 %14) #1
  %ld.s14 = call i134 @hwtHls.bitConcat.i128.i6(i128 %12, i6 %11) #1
  %r2.eof.0lane = icmp ne i134 %ld.s03, 0
  %r2.ext.0lane = zext i134 %ld.s03 to i135
  store volatile i135 %r2.ext.0lane, ptr addrspace(2) %tx, align 32
  br i1 %r2.eof.0lane, label %bb.consumePendingOnLast.0lane, label %bb.forwardUntilEoF.streamSegSplit.0lane

bb.forwardUntilEoF.1lane:                         ; preds = %bb.forwardUntilEoF.streamSegSplit.0lane
  %r2.eof.1lane = icmp ne i134 %rx.1segment.1, 0
  %r2.ext.1lane = zext i134 %rx.1segment.1 to i135
  store volatile i135 %r2.ext.1lane, ptr addrspace(2) %tx, align 32
  br i1 %r2.eof.1lane, label %bb.consumePendingOnLast.1lane, label %bb.forwardUntilEoF.streamSegSplit.1lane

bb.consumePendingOnLast.0lane:                    ; preds = %bb.forwardUntilEoF.0lane
  %r.phi.lcssa.0lane = phi i134 [ %r.phi.1lane, %bb.forwardUntilEoF.0lane ]
  %r.phi.ext.0lane = zext i134 %r.phi.lcssa.0lane to i135
  store volatile i135 %r.phi.ext.0lane, ptr addrspace(2) %tx, align 32
  br label %bb1.backedge.0lane

bb.consumePendingOnLast.1lane:                    ; preds = %bb.forwardUntilEoF.1lane
  %r.phi.lcssa.1lane = phi i134 [ %r.phi.0lane, %bb.forwardUntilEoF.1lane ]
  %r.phi.ext.1lane = zext i134 %r.phi.lcssa.1lane to i135
  store volatile i135 %r.phi.ext.1lane, ptr addrspace(2) %tx, align 32
  br label %bb1.backedge.1lane

bb1.backedge.0lane:                               ; preds = %bb.consumePendingOnLast.0lane, %bb1.0lane
  %rx.1segment.0 = phi i134 [ %ld.s1, %bb1.0lane ], [ %ld.s14, %bb.consumePendingOnLast.0lane ]
  br label %bb1.streamSegSplit.0lane

bb1.backedge.1lane:                               ; preds = %bb.consumePendingOnLast.1lane, %bb1.1lane
  br label %bb1.streamSegSplit.1lane, !llvm.loop !5
}
