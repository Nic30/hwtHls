define void @LoopFlattenUsingIfPass_ir_TC.test_1loop(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.pktLoop.head

bb.pktLoop.head:                                  ; preds = %txConsumePendingOnLast, %bb0
  %rx_read6.r0 = load volatile i133, ptr addrspace(1) %rx, align 32
  %rx_read6.r0.eof = call i1 @hwtHls.bitRangeGet.i133.i9.i1.128(i133 %rx_read6.r0, i9 128) #4
  %rx_read6.r0.empty = call i4 @hwtHls.bitRangeGet.i133.i9.i4.129(i133 %rx_read6.r0, i9 129) #4
  %0 = icmp eq i4 %rx_read6.r0.empty, 0
  %NonEoFImplEmptyEq0 = or i1 %rx_read6.r0.eof, %0
  call void @llvm.assume(i1 %NonEoFImplEmptyEq0)
  %rx_read6.r1 = load volatile i133, ptr addrspace(1) %rx, align 32
  %rx_read6.r1.data = call i128 @hwtHls.bitRangeGet.i133.i9.i128.0(i133 %rx_read6.r1, i9 0) #4
  %rx_read6.r1.eof = call i1 @hwtHls.bitRangeGet.i133.i9.i1.128(i133 %rx_read6.r1, i9 128) #4
  %rx_read6.r1.empty = call i4 @hwtHls.bitRangeGet.i133.i9.i4.129(i133 %rx_read6.r1, i9 129) #4
  %1 = icmp eq i4 %rx_read6.r1.empty, 0
  %NonEoFImplEmptyEq013 = or i1 %rx_read6.r1.eof, %1
  call void @llvm.assume(i1 %NonEoFImplEmptyEq013)
  br label %bb.forwardUntilEoF.axi4ss.head

bb.forwardUntilEoF.axi4ss.head:                   ; preds = %bb.forwardUntilEoF.axi4ss.head.latch, %bb.pktLoop.head
  %txData.0 = phi i128 [ undef, %bb.pktLoop.head ], [ %12, %bb.forwardUntilEoF.axi4ss.head.latch ]
  %rxDataEoF.0 = phi i1 [ %rx_read6.r1.eof, %bb.pktLoop.head ], [ %rx_read5.r1.eof, %bb.forwardUntilEoF.axi4ss.head.latch ]
  %rxData.0 = phi i128 [ %rx_read6.r1.data, %bb.pktLoop.head ], [ %rx_read5.r1.data, %bb.forwardUntilEoF.axi4ss.head.latch ]
  %2 = call i112 @hwtHls.bitRangeGet.i128.i8.i112.16(i128 %rxData.0, i8 16) #4
  %3 = call i16 @hwtHls.bitRangeGet.i128.i8.i16.16(i128 %rxData.0, i8 16) #4
  %4 = call i112 @hwtHls.bitRangeGet.i128.i8.i112.0(i128 %txData.0, i8 0) #4
  %rx_read5.r1 = load volatile i133, ptr addrspace(1) %rx, align 32
  %rx_read5.r1.data = call i128 @hwtHls.bitRangeGet.i133.i9.i128.0(i133 %rx_read5.r1, i9 0) #4
  %5 = call i16 @hwtHls.bitRangeGet.i133.i9.i16.0(i133 %rx_read5.r1, i9 0) #4
  %rx_read5.r1.eof = call i1 @hwtHls.bitRangeGet.i133.i9.i1.128(i133 %rx_read5.r1, i9 128) #4
  %rx_read5.r1.empty = call i4 @hwtHls.bitRangeGet.i133.i9.i4.129(i133 %rx_read5.r1, i9 129) #4
  %6 = icmp eq i4 %rx_read5.r1.empty, 0
  %NonEoFImplEmptyEq016 = or i1 %rx_read5.r1.eof, %6
  call void @llvm.assume(i1 %NonEoFImplEmptyEq016)
  %7 = icmp ugt i4 %rx_read5.r1.empty, -3
  %8 = and i1 %rx_read5.r1.eof, %7
  %9 = or i1 %rxDataEoF.0, %8
  %"(rx_read5)" = call i133 @hwtHls.bitConcat.i112.i16.i1.i4(i112 %2, i16 %5, i1 %9, i4 0) #4
  %10 = call i112 @hwtHls.bitRangeGet.i133.i9.i112.16(i133 %"(rx_read5)", i9 16) #4
  %11 = call i134 @hwtHls.bitConcat.i112.i16.i6(i112 %4, i16 %3, i6 24) #4
  store volatile i134 %11, ptr addrspace(2) %tx, align 32
  %12 = call i128 @hwtHls.bitConcat.i112.i16(i112 %10, i16 undef) #4
  br i1 %9, label %txConsumePendingOnLast, label %bb.forwardUntilEoF.axi4ss.head.latch

bb.forwardUntilEoF.axi4ss.head.latch:             ; preds = %bb.forwardUntilEoF.axi4ss.head
  br label %bb.forwardUntilEoF.axi4ss.head

txConsumePendingOnLast:                           ; preds = %bb.forwardUntilEoF.axi4ss.head
  %.lcssa = phi i112 [ %10, %bb.forwardUntilEoF.axi4ss.head ]
  %13 = call i134 @hwtHls.bitConcat.i112.i16.i6(i112 %.lcssa, i16 undef, i6 29) #4
  store volatile i134 %13, ptr addrspace(2) %tx, align 32
  br label %bb.pktLoop.head, !llvm.loop !6
}
