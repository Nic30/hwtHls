define void @phiInitToUndef0a(ptr addrspace(1) %dout, ptr addrspace(3) %timerTick, ptr addrspace(4) %uart) {
bb11:
  br label %bb14

bb14:                                             ; preds = %bb14, %bb11
  %shiftPhi1 = phi i6 [ undef, %bb11 ], [ %data0, %bb14 ]
  %0 = call i5 @hwtHls.bitRangeGet.i6.i4.i5.1(i6 %shiftPhi1, i4 1) #1
  %uart0 = load volatile i1, ptr addrspace(4) %uart, align 1
  %1 = call i7 @hwtHls.bitConcat.i6.i1(i6 %shiftPhi1, i1 %uart0) #1
  store volatile i7 %1, ptr addrspace(1) %dout, align 1
  %data0 = call i6 @hwtHls.bitConcat.i5.i1(i5 %0, i1 %uart0) #1
  br label %bb14
}
