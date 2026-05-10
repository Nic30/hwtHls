define void @test_preserveBrCond_0(ptr addrspace(1) %crcOut, ptr addrspace(2) %i) {
bb0:
  br label %bb.L1.head

bb.L1.head:                                       ; preds = %bb0, %bb.L0.latch, %bb.L1.2
  %crcAcc.0 = phi i32 [ -1, %bb0 ], [ -1, %bb.L0.latch ], [ %15, %bb.L1.2 ]
  %i_read1.r0 = load volatile i37, ptr addrspace(2) %i, align 8
  %0 = call i2 @hwtHls.bitRangeGet.i37.i7.i2.33(i37 %i_read1.r0, i7 33) #2
  %1 = call i16 @hwtHls.bitRangeGet.i37.i7.i16.0(i37 %i_read1.r0, i7 0) #2
  %2 = call i16 @hwtHls.bitRangeGet.i37.i7.i16.16(i37 %i_read1.r0, i7 16) #2
  %3 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %i_read1.r0, i7 35) #2
  %i_read1.r0.eof = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %i_read1.r0, i7 36) #2
  %4 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %i_read1.r0, i7 33) #2
  %5 = xor i1 %4, true
  %6 = and i1 %i_read1.r0.eof, %5
  %7 = xor i1 %6, true
  %8 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %7) #2
  %9 = call i32 @hwtHls.pyObjectPlaceholder.0.crc.CRC_32.i16(i32 0, i32 %crcAcc.0, i16 %1, i2 %8) #2
  %10 = xor i1 %3, true
  %11 = and i1 %i_read1.r0.eof, %10
  %12 = xor i1 %11, true
  %13 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %12) #2
  %14 = icmp ne i2 %0, -1
  %brmerge1 = and i1 %i_read1.r0.eof, %14
  br i1 %brmerge1, label %bb.L0.latch, label %bb.L1.2

bb.L1.2:                                          ; preds = %bb.L1.head
  %15 = call i32 @hwtHls.pyObjectPlaceholder.0.crc.CRC_32.i16(i32 0, i32 %9, i16 %2, i2 %13) #2
  br i1 %i_read1.r0.eof, label %bb.L0.latch, label %bb.L1.head

bb.L0.latch:                                      ; preds = %bb.L1.head, %bb.L1.2
  %.lcssa = phi i32 [ %9, %bb.L1.head ], [ %15, %bb.L1.2 ]
  %16 = call i32 @hwtHls.pyObjectPlaceholder.1.CrcFinalizeHardblock.i32(i32 1, i32 %.lcssa) #2
  store volatile i32 %16, ptr addrspace(1) %crcOut, align 4
  br label %bb.L1.head
}
