define void @test_streamWriteMerge_variableLenWrite2(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !hwtHls.io !0 {
bb0:
  %txDataOffset = alloca i5, align 1
  call void @hwtHls.streamTmpAllocaTmpSetterPlaceholder.p0(ptr %txDataOffset)
  br label %mainLoop

mainLoop:                                         ; preds = %bb.ret, %bb0
  %.r0 = load volatile i28, ptr addrspace(1) %rx, align 4
  %0 = call i24 @hwtHls.bitRangeGet.i28.i6.i24.0(i28 %.r0, i6 0) #3
  %.eof = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %.r0, i6 27) #3
  %1 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.25(i28 %.r0, i6 25) #3
  %2 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.24(i28 %.r0, i6 24) #3
  %3 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.26(i28 %.r0, i6 26) #3
  %.mask = call i3 @hwtHls.bitRangeGet.i28.i6.i3.24(i28 %.r0, i6 24) #3
  %4 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.26(i28 %.r0, i6 26) #3
  %.specExit63 = icmp ne i2 %4, -2
  %5 = xor i1 %.eof, true
  %.specExit = or i1 %5, %1
  %prevMaskBit1Impl = icmp ule i1 %1, %2
  call void @llvm.assume(i1 %prevMaskBit1Impl)
  %NonEoFImplMaskBit151 = or i1 %.eof, %1
  call void @llvm.assume(i1 %NonEoFImplMaskBit151)
  %prevMaskBit1Impl52 = icmp ule i1 %3, %1
  call void @llvm.assume(i1 %prevMaskBit1Impl52)
  %prevMaskBit1Impl53 = icmp ule i1 %3, %2
  call void @llvm.assume(i1 %prevMaskBit1Impl53)
  %NonEoFImplMaskBit154 = icmp ne i2 %4, 0
  call void @llvm.assume(i1 %NonEoFImplMaskBit154)
  %6 = icmp eq i3 %.mask, -1
  %NonEoFImplMaskAll155 = or i1 %.eof, %6
  call void @llvm.assume(i1 %NonEoFImplMaskAll155)
  %7 = xor i1 %3, true
  %.specExit65 = and i1 %.eof, %7
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #4
  %8 = xor i1 %.specExit65, true
  %9 = and i1 %8, %.specExit63
  %10 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 true, i1 %.specExit, i1 %9) #3
  call void @hwtHls.streamWrite.masked.p2.i24.i3.i1.i1.p0(ptr addrspace(2) %tx, i24 %0, i3 %10, i1 false, i1 %.eof, ptr null) #4
  br i1 %.eof, label %bb.ret, label %copyLoop

copyLoop:                                         ; preds = %copyLoop, %mainLoop
  %cp.r = load volatile i28, ptr addrspace(1) %rx, align 4
  %11 = call i24 @hwtHls.bitRangeGet.i28.i6.i24.0(i28 %cp.r, i6 0) #3
  %12 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.25(i28 %cp.r, i6 25) #3
  %cp.eof = call i1 @hwtHls.bitRangeGet.i28.i6.i1.27(i28 %cp.r, i6 27) #3
  %cp.mask1 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.25(i28 %cp.r, i6 25) #3
  %cp.mask0 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.24(i28 %cp.r, i6 24) #3
  %cp.mask2 = call i1 @hwtHls.bitRangeGet.i28.i6.i1.26(i28 %cp.r, i6 26) #3
  %cp.mask = call i3 @hwtHls.bitRangeGet.i28.i6.i3.24(i28 %cp.r, i6 24) #3
  %13 = call i2 @hwtHls.bitRangeGet.i28.i6.i2.26(i28 %cp.r, i6 26) #3
  %prevMaskBit1Impl57 = icmp ule i1 %cp.mask1, %cp.mask0
  call void @llvm.assume(i1 %prevMaskBit1Impl57)
  %NonEoFImplMaskBit158 = or i1 %cp.eof, %cp.mask1
  call void @llvm.assume(i1 %NonEoFImplMaskBit158)
  %prevMaskBit1Impl59 = icmp ule i1 %cp.mask2, %cp.mask1
  call void @llvm.assume(i1 %prevMaskBit1Impl59)
  %prevMaskBit1Impl60 = icmp ule i1 %cp.mask2, %cp.mask0
  call void @llvm.assume(i1 %prevMaskBit1Impl60)
  %NonEoFImplMaskBit161 = icmp ne i2 %13, 0
  call void @llvm.assume(i1 %NonEoFImplMaskBit161)
  %14 = icmp eq i3 %cp.mask, -1
  %NonEoFImplMaskAll162 = or i1 %cp.eof, %14
  call void @llvm.assume(i1 %NonEoFImplMaskAll162)
  %cp.tx.mask2 = icmp ne i2 %13, -2
  %cp.eof_n = xor i1 %cp.eof, true
  %cp.tx.mask1 = or i1 %cp.eof_n, %cp.mask1
  %cp.tx.mask0 = or i1 %cp.eof_n, %cp.mask0
  %15 = icmp ne i2 %12, -1
  %16 = and i1 %cp.eof, %15
  %17 = xor i1 %16, true
  %18 = and i1 %17, %cp.tx.mask2
  %19 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %cp.tx.mask0, i1 %cp.tx.mask1, i1 %18) #3
  call void @hwtHls.streamWrite.masked.p2.i24.i3.i1.i1.p0(ptr addrspace(2) %tx, i24 %11, i3 %19, i1 false, i1 %cp.eof, ptr null) #4
  br i1 %cp.eof, label %bb.ret, label %copyLoop

bb.ret:                                           ; preds = %copyLoop, %mainLoop
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #4
  br label %mainLoop
}
