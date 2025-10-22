define void @test_preserveBrCond_0(ptr addrspace(1) %crcOut, ptr addrspace(2) %i) {
bb0:
  br label %bb.L1.head

bb.L1.head:                                       ; preds = %bb.L1.head, %bb0, %bb.L0.latch
  %crcAcc.0 = phi i32 [ -1, %bb0 ], [ -1, %bb.L0.latch ], [ %16, %bb.L1.head ]
  %i_read1.r0 = load volatile i37, ptr addrspace(2) %i, align 8
  %0 = call i32 @hwtHls.bitRangeGet.i37.i7.i32.0(i37 %i_read1.r0, i7 0) #3
  %1 = call i2 @hwtHls.bitRangeGet.i37.i7.i2.33(i37 %i_read1.r0, i7 33) #3
  %2 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %i_read1.r0, i7 35) #3
  %i_read1.r0.eof = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %i_read1.r0, i7 36) #3
  %3 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %i_read1.r0, i7 33) #3
  %4 = xor i1 %3, true
  %5 = and i1 %i_read1.r0.eof, %4
  %6 = xor i1 %5, true
  %7 = icmp ne i2 %1, -1
  %8 = and i1 %i_read1.r0.eof, %7
  %9 = xor i1 %2, true
  %10 = and i1 %i_read1.r0.eof, %9
  %11 = xor i1 %10, true
  %12 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %11) #3
  %13 = select i1 %8, i2 0, i2 %12
  %14 = call i4 @hwtHls.bitConcat.i1.i1.i2(i1 true, i1 %6, i2 %13) #3
  %.lcssa = call i32 @hwtHls.pyObjectPlaceholder.0.crc.CRC_32.i32(i32 0, i32 %crcAcc.0, i32 %0, i4 %14) #3
  %15 = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 true, i1 %6, i1 true, i1 %11) #3
  %16 = call i32 @hwtHls.pyObjectPlaceholder.0.crc.CRC_32.i32(i32 0, i32 %crcAcc.0, i32 %0, i4 %15) #3
  %brmerge1 = and i1 %i_read1.r0.eof, %7
  %impCache = icmp ule i1 %brmerge1, %i_read1.r0.eof
  call void @llvm.assume(i1 %impCache)
  br i1 %i_read1.r0.eof, label %bb.L0.latch, label %bb.L1.head

bb.L0.latch:                                      ; preds = %bb.L1.head
  %17 = call i32 @hwtHls.pyObjectPlaceholder.1.CrcFinalizeHardblock.i32(i32 1, i32 %.lcssa) #3
  store volatile i32 %17, ptr addrspace(1) %crcOut, align 4
  br label %bb.L1.head
}
