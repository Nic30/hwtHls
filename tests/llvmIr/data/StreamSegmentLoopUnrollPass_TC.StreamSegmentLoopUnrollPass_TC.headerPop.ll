define void @StreamSegmentLoopUnrollPass_TC.headerPop(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1.backedge, %bb0
  %r0 = load volatile i134, ptr addrspace(1) %rx, align 32
  %r0.eof = icmp ne i134 %r0, 0
  br i1 %r0.eof, label %bb1.backedge, label %bb1.segmentEnCheck.after

bb1.backedge:                                     ; preds = %bb.consumePendingOnLast, %bb1
  br label %bb1

bb1.segmentEnCheck.after:                         ; preds = %bb1
  %r1 = load volatile i134, ptr addrspace(1) %rx, align 32
  br label %bb.forwardUntilEoF.streamSegSplit.1lane

bb.forwardUntilEoF.streamSegSplit.0lane:          ; preds = %bb.forwardUntilEoF.0lane
  br label %bb.forwardUntilEoF.1lane

bb.forwardUntilEoF.streamSegSplit.1lane:          ; preds = %bb.forwardUntilEoF.1lane, %bb1.segmentEnCheck.after
  %r.phi.reg2mem.0 = phi i134 [ %r1, %bb1.segmentEnCheck.after ], [ %6, %bb.forwardUntilEoF.1lane ]
  br label %bb.forwardUntilEoF.0lane

bb.forwardUntilEoF.0lane:                         ; preds = %bb.forwardUntilEoF.streamSegSplit.1lane
  %0 = load volatile i268, ptr addrspace(1) %rx, align 64
  %1 = call i6 @hwtHls.bitRangeGet.i268.i10.i6.6(i268 %0, i10 6) #1
  %2 = call i128 @hwtHls.bitRangeGet.i268.i10.i128.128(i268 %0, i10 128) #1
  %3 = call i128 @hwtHls.bitRangeGet.i268.i10.i128.0(i268 %0, i10 0) #1
  %4 = call i6 @hwtHls.bitRangeGet.i268.i10.i6.0(i268 %0, i10 0) #1
  %5 = call i134 @hwtHls.bitConcat.i128.i6(i128 %3, i6 %4) #1
  %6 = call i134 @hwtHls.bitConcat.i128.i6(i128 %2, i6 %1) #1
  %r2.eof.0lane = icmp ne i134 %5, 0
  %r2.ext.0lane = zext i134 %5 to i135
  store volatile i135 %r2.ext.0lane, ptr addrspace(2) %tx, align 32
  br i1 %r2.eof.0lane, label %bb.consumePendingOnLast, label %bb.forwardUntilEoF.streamSegSplit.0lane

bb.forwardUntilEoF.1lane:                         ; preds = %bb.forwardUntilEoF.streamSegSplit.0lane
  %r2.eof.1lane = icmp ne i134 %6, 0
  %r2.ext.1lane = zext i134 %6 to i135
  store volatile i135 %r2.ext.1lane, ptr addrspace(2) %tx, align 32
  br i1 %r2.eof.1lane, label %bb.consumePendingOnLast, label %bb.forwardUntilEoF.streamSegSplit.1lane, !llvm.loop !5

bb.consumePendingOnLast:                          ; preds = %bb.forwardUntilEoF.0lane, %bb.forwardUntilEoF.1lane
  %r.phi.lcssa.reg2mem.0 = phi i134 [ %r.phi.reg2mem.0, %bb.forwardUntilEoF.0lane ], [ %5, %bb.forwardUntilEoF.1lane ]
  %r.phi.ext = zext i134 %r.phi.lcssa.reg2mem.0 to i135
  store volatile i135 %r.phi.ext, ptr addrspace(2) %tx, align 32
  br label %bb1.backedge
}
