define void @test_streamWriteMerge_variableLenWrite1(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !hwtHls.io !0 {
bb0:
  %txDataOffset = alloca i5, align 1
  call void @hwtHls.streamTmpAllocaTmpSetterPlaceholder.p0(ptr %txDataOffset)
  br label %mainLoop

mainLoop:                                         ; preds = %_forwardPacket.ret, %bb0
  %.r0 = load volatile i28, ptr addrspace(1) %rx, align 4
  %0 = call i24 @hwtHls.bitRangeGet.i28.i6.i24.0(i28 %.r0, i6 0) #3
  %.eof = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %.r0, i6 27) #3
  %1 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.25(i28 %.r0, i6 25) #3
  %2 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.24(i28 %.r0, i6 24) #3
  %3 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.26(i28 %.r0, i6 26) #3
  %.mask = call i3 @hwtHls.bitRangeGet.i28.i6.i3.24(i28 %.r0, i6 24) #3
  %4 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.26(i28 %.r0, i6 26) #3
  %.specExit64 = icmp ne i2 %4, -2
  %prevMaskBit1Impl = icmp ule i1 %1, %2
  call void @llvm.assume(i1 %prevMaskBit1Impl)
  %NonEoFImplMaskBit152 = or i1 %.eof, %1
  call void @llvm.assume(i1 %NonEoFImplMaskBit152)
  %prevMaskBit1Impl53 = icmp ule i1 %3, %1
  call void @llvm.assume(i1 %prevMaskBit1Impl53)
  %prevMaskBit1Impl54 = icmp ule i1 %3, %2
  call void @llvm.assume(i1 %prevMaskBit1Impl54)
  %NonEoFImplMaskBit155 = icmp ne i2 %4, 0
  call void @llvm.assume(i1 %NonEoFImplMaskBit155)
  %5 = icmp eq i3 %.mask, -1
  %NonEoFImplMaskAll156 = or i1 %.eof, %5
  call void @llvm.assume(i1 %NonEoFImplMaskAll156)
  %6 = xor i1 %3, true
  %.specExit67 = and i1 %.eof, %6
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #4
  %7 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %1) #3
  %8 = sext i1 %.eof to i2
  %9 = xor i2 %8, -1
  %.specExit = or i2 %9, %7
  %10 = xor i1 %.specExit67, true
  %11 = and i1 %10, %.specExit64
  %12 = call i3 @hwtHls.bitConcat.i2.i1(i2 %.specExit, i1 %11) #3
  call void @hwtHls.streamWrite.masked.p2.i24.i3.i1.i1.p0(ptr addrspace(2) %tx, i24 %0, i3 %12, i1 false, i1 %.eof, ptr null) #4
  br i1 %.eof, label %_forwardPacket.ret, label %copyLoop

copyLoop:                                         ; preds = %mainLoop, %copyLoop
  %r1 = load volatile i28, ptr addrspace(1) %rx, align 4
  %.eof43 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %r1, i6 27) #3
  br i1 %.eof43, label %_forwardPacket.ret, label %copyLoop

_forwardPacket.ret:                               ; preds = %mainLoop, %copyLoop
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %mainLoop
}
