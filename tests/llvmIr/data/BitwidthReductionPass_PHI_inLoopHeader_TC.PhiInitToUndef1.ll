define void @PhiInitToUndef1(ptr addrspace(1) %dout, ptr addrspace(3) %timerTick, ptr addrspace(4) %uart) {
bb11:
  br label %bb14

bb14:                                             ; preds = %bb24, %bb11
  %cntr0 = phi i4 [ %"37", %bb24 ], [ 7, %bb11 ]
  %shiftPhi1 = phi i6 [ %data0, %bb24 ], [ undef, %bb11 ]
  %0 = call i5 @hwtHls.bitRangeGet.i6.i4.i5.1(i6 %shiftPhi1, i4 1) #1
  br label %bb16

bb16:                                             ; preds = %bb17, %bb14
  %timerTick.0 = load volatile i1, ptr addrspace(3) %timerTick, align 1
  br i1 %timerTick.0, label %bb20, label %bb17

bb17:                                             ; preds = %bb16
  br label %bb16

bb20:                                             ; preds = %bb21, %bb16
  %timerTick.1 = load volatile i1, ptr addrspace(3) %timerTick, align 1
  br i1 %timerTick.1, label %bb24, label %bb21

bb21:                                             ; preds = %bb20
  br label %bb20

bb24:                                             ; preds = %bb20
  %uart0 = load volatile i1, ptr addrspace(4) %uart, align 1
  %"37" = add nsw i4 %cntr0, -1
  %"38" = icmp sgt i4 %cntr0, 0
  %1 = call i7 @hwtHls.bitConcat.i6.i1(i6 %shiftPhi1, i1 %uart0) #1
  store volatile i7 %1, ptr addrspace(1) %dout, align 1
  %data0 = call i6 @hwtHls.bitConcat.i5.i1(i5 %0, i1 %uart0) #1
  br i1 %"38", label %bb14, label %bb27

bb27:                                             ; preds = %bb24
  ret void
}
