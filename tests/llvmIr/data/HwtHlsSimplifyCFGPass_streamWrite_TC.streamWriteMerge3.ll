define void @streamWriteMerge3(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %bb.writeExit.1, %bb0
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #3
  br label %loop.pkt.read

loop.pkt.read:                                    ; preds = %bb.writeExit, %loop.pkt
  %curLen.015 = phi i11 [ 0, %loop.pkt ], [ %curLen.116.2, %bb.writeExit ]
  %.w0 = load volatile i28, ptr addrspace(1) %rx, align 4
  %0 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.0(i28 %.w0, i6 0) #4
  %1 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.25(i28 %.w0, i6 25) #4
  %2 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %.w0, i6 27) #4
  %3 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.16(i28 %.w0, i6 16) #4
  %4 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.26(i28 %.w0, i6 26) #4
  %5 = call i8 @hwtHls.bitRangeGet.i28.i6.i8.8(i28 %.w0, i6 8) #4
  %6 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.25(i28 %.w0, i6 25) #4
  %7 = xor i1 %6, true
  %8 = and i1 %2, %7
  %write0.en = icmp ne i11 %curLen.015, -648
  %9 = icmp eq i11 %curLen.015, -649
  %10 = xor i1 %4, true
  %11 = and i1 %2, %10
  %sig_7.1 = or i1 %11, %9
  %.025 = and i1 %write0.en, %sig_7.1
  %12 = add i11 %curLen.015, 2
  %curLen.116.1 = select i1 %write0.en, i11 %12, i11 -648
  %sig_7.2 = or i1 %2, %9
  %.031 = and i1 %write0.en, %sig_7.2
  %sig_8.2 = zext i1 %write0.en to i11
  %curLen.116.2 = add i11 %curLen.116.1, %sig_8.2
  %13 = xor i1 %8, true
  %14 = icmp ne i2 %1, -1
  %15 = and i1 %2, %14
  %16 = xor i1 %15, true
  %write2.en = and i1 %16, %write0.en
  %eof.2 = and i1 %16, %.031
  %.230 = select i1 %15, i8 undef, i8 %3
  %write1.en = and i1 %write0.en, %13
  %eof.1 = and i1 %.025, %13
  %.2 = select i1 %8, i8 undef, i8 %5
  %sig_7 = or i1 %8, %9
  %17 = or i1 %sig_7, %eof.1
  br i1 %write0.en, label %bb.write2, label %bb.writeExit

bb.write2:                                        ; preds = %loop.pkt.read
  %18 = call i24 @hwtHls.bitConcat.i8.i8.i8(i8 %0, i8 %.2, i8 %.230) #4
  %19 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %write0.en, i1 %write1.en, i1 %write2.en) #4
  %20 = or i1 %17, %eof.2
  call void @hwtHls.streamWrite.masked.p2.i24.i3.i1(ptr addrspace(2) %tx, i24 %18, i3 %19, i1 %20) #3
  br label %bb.writeExit

bb.writeExit:                                     ; preds = %bb.write2, %loop.pkt.read
  br i1 %2, label %bb.writeExit.1, label %loop.pkt.read

bb.writeExit.1:                                   ; preds = %bb.writeExit
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #3
  br label %loop.pkt
}
