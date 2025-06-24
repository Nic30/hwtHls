define void @StreamReadLoweringPass_TC.test_copy2B(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !hwtHls.param_addr_width !0 !hwtHls.streamIo !2 {
bb0:
  br label %bb.rx.sof

bb.rx.sof:                                        ; preds = %bb.eof, %bb0
  %rxDataEoF.0 = phi i1 [ undef, %bb0 ], [ %rxDataEoF.2, %bb.eof ]
  %rxDataMask.0 = phi i2 [ undef, %bb0 ], [ %rxDataMask.2, %bb.eof ]
  %rxData.0 = phi i16 [ undef, %bb0 ], [ %rxData.2, %bb.eof ]
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #3
  br label %bb.rx.read

bb.rx.read:                                       ; preds = %bb.rx.eofCheck, %bb.rx.sof
  %rxDataOffset.0 = phi i4 [ 0, %bb.rx.sof ], [ %rxDataOffset.2, %bb.rx.eofCheck ]
  %rxDataEoF.1 = phi i1 [ %rxDataEoF.0, %bb.rx.sof ], [ %rxDataEoF.2, %bb.rx.eofCheck ]
  %rxDataMask.1 = phi i2 [ %rxDataMask.0, %bb.rx.sof ], [ %rxDataMask.2, %bb.rx.eofCheck ]
  %rxData.1 = phi i16 [ %rxData.0, %bb.rx.sof ], [ %rxData.2, %bb.rx.eofCheck ]
  %0 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %rxData.1, i5 0) #4
  %1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %rxDataMask.1, i2 0) #4
  %2 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %rxDataMask.1, i2 1) #4
  %"(readEn)" = icmp eq i4 %rxDataOffset.0, 0
  br i1 %"(readEn)", label %3, label %7

3:                                                ; preds = %bb.rx.read
  %rx_read1.opt = load volatile i19, ptr addrspace(1) %rx, align 4
  %rx_read1.opt.data = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %rx_read1.opt, i6 0) #4
  %rx_read1.opt.eof = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rx_read1.opt, i6 18) #4
  %rx_read1.opt.mask = call i2 @hwtHls.bitRangeGet.i19.i6.i2.16(i19 %rx_read1.opt, i6 16) #4
  %4 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %rx_read1.opt, i6 16) #4
  %5 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %rx_read1.opt, i6 17) #4
  %prevMaskBit1Impl = icmp ule i1 %5, %4
  call void @llvm.assume(i1 %prevMaskBit1Impl)
  %NonEoFImplMaskBit1 = or i1 %rx_read1.opt.eof, %5
  call void @llvm.assume(i1 %NonEoFImplMaskBit1)
  %6 = icmp eq i2 %rx_read1.opt.mask, -1
  %NonEoFImplMaskAll1 = or i1 %rx_read1.opt.eof, %6
  call void @llvm.assume(i1 %NonEoFImplMaskAll1)
  br label %7

7:                                                ; preds = %bb.rx.read, %3
  %rxDataEoF.2 = phi i1 [ %rx_read1.opt.eof, %3 ], [ %rxDataEoF.1, %bb.rx.read ]
  %rxDataMask.2 = phi i2 [ %rx_read1.opt.mask, %3 ], [ %rxDataMask.1, %bb.rx.read ]
  %rxData.2 = phi i16 [ %rx_read1.opt.data, %3 ], [ %rxData.1, %bb.rx.read ]
  %8 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %rxData.2, i5 8) #4
  %9 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %rxDataMask.2, i2 1) #4
  %10 = icmp eq i4 %rxDataOffset.0, 0
  br i1 %10, label %rxoff0, label %16

rxoff0:                                           ; preds = %7
  %11 = xor i1 %2, true
  %12 = and i1 %rxDataEoF.1, %11
  %13 = xor i1 %2, true
  %14 = and i1 %12, %13
  %"(rx_read1)" = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %0, i1 %1, i1 %14) #4
  br i1 %12, label %"(rx_read1)Last", label %"(rx_read1)NoLast"

"(rx_read1)Last":                                 ; preds = %rxoff0
  br label %15

"(rx_read1)NoLast":                               ; preds = %rxoff0
  br label %15

15:                                               ; preds = %"(rx_read1)NoLast", %"(rx_read1)Last"
  %rxDataOffset.1 = phi i4 [ 0, %"(rx_read1)Last" ], [ -8, %"(rx_read1)NoLast" ]
  br label %20

16:                                               ; preds = %7
  %17 = icmp eq i4 %rxDataOffset.0, -8
  br i1 %17, label %rxoff8, label %18

rxoff8:                                           ; preds = %16
  %"(rx_read1)6" = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %8, i1 %9, i1 %rxDataEoF.2) #4
  br label %19

18:                                               ; preds = %16
  unreachable

19:                                               ; preds = %rxoff8
  br label %20

20:                                               ; preds = %19, %15
  %rx_read14.0 = phi i10 [ %"(rx_read1)", %15 ], [ %"(rx_read1)6", %19 ]
  %rxDataOffset.2 = phi i4 [ %rxDataOffset.1, %15 ], [ 0, %19 ]
  %rx_read_last4 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read14.0, i5 9) #4
  %rx_read_data = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read14.0, i5 0) #4
  %rx_read_strb = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %rx_read14.0, i5 8) #4
  br i1 %rx_read_strb, label %bb.tx.write, label %bb.rx.eofCheck

bb.tx.write:                                      ; preds = %20
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %rx_read_data, i1 %rx_read_last4) #3
  br label %bb.rx.eofCheck

bb.rx.eofCheck:                                   ; preds = %bb.tx.write, %20
  br i1 %rx_read_last4, label %bb.eof, label %bb.rx.read

bb.eof:                                           ; preds = %bb.rx.eofCheck
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #3
  br label %bb.rx.sof
}
