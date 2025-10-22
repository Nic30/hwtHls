define void @test_tryReduceOrOfAssumedPredicates(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  %.r0 = load volatile i28, ptr addrspace(1) %rx, align 4
  %.eof = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %.r0, i6 27) #3
  %0 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.25(i28 %.r0, i6 25) #3
  %1 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.26(i28 %.r0, i6 26) #3
  %.mask = call i3 @hwtHls.bitRangeGet.i28.i6.i3.24(i28 %.r0, i6 24) #3
  %2 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.26(i28 %.r0, i6 26) #3
  %3 = call i24 @hwtHls.bitRangeGet.i28.i6.i24.0(i28 %.r0, i6 0) #3
  %4 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.25(i28 %.r0, i6 25) #3
  %prevMaskBit1Impl54 = icmp ule i1 %1, %0
  call void @llvm.assume(i1 %prevMaskBit1Impl54)
  %NonEoFImplMaskBit153 = or i1 %.eof, %0
  call void @llvm.assume(i1 %NonEoFImplMaskBit153)
  %NonEoFImplMaskBit156 = icmp ne i2 %2, 0
  call void @llvm.assume(i1 %NonEoFImplMaskBit156)
  %5 = icmp eq i3 %.mask, -1
  %6 = xor i1 %5, true
  %NonEoFImplMaskAll157 = or i1 %.eof, %5
  call void @llvm.assume(i1 %NonEoFImplMaskAll157)
  %7 = or i1 %6, %.eof
  call void @llvm.assume(i1 %7)
  %8 = call i3 @hwtHls.bitConcat.i1.i2(i1 true, i2 %4) #3
  %9 = xor i1 %.eof, true
  %10 = sext i1 %9 to i3
  %.specExit = or i3 %10, %8
  call void @hwtHls.streamWrite.masked.p2.i24.i3.i1.i1(ptr addrspace(2) %tx, i24 %3, i3 %.specExit, i1 false, i1 %.eof) #4
  ret void
}
