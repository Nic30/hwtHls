define void @test_phiToLogicalExp1(ptr addrspace(1) %rx, ptr addrspace(2) %out) {
bb.0:
  %.r0 = load volatile i37, ptr addrspace(1) %rx, align 8
  %0 = call i2 @hwtHls.bitRangeGet.i37.i7.i2.33(i37 %.r0, i7 33) #2
  %1 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.r0, i7 33) #2
  %.eof51 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.r0, i7 36) #2
  %2 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %.r0, i7 32) #2
  %3 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.34(i37 %.r0, i7 34) #2
  %4 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %.r0, i7 35) #2
  %.mask52 = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %.r0, i7 32) #2
  %5 = call i2 @hwtHls.bitRangeGet.i37.i7.i2.35(i37 %.r0, i7 35) #2
  %.mask = call i3 @hwtHls.bitRangeGet.i37.i7.i3.33(i37 %.r0, i7 33) #2
  %prevMaskBit1Impl62 = icmp ule i1 %1, %2
  call void @llvm.assume(i1 %prevMaskBit1Impl62)
  %NonEoFImplMaskBit1 = or i1 %.eof51, %1
  call void @llvm.assume(i1 %NonEoFImplMaskBit1)
  %prevMaskBit1Impl63 = icmp ule i1 %3, %1
  call void @llvm.assume(i1 %prevMaskBit1Impl63)
  %prevMaskBit1Impl64 = icmp ule i1 %3, %2
  call void @llvm.assume(i1 %prevMaskBit1Impl64)
  %NonEoFImplMaskBit165 = or i1 %.eof51, %3
  call void @llvm.assume(i1 %NonEoFImplMaskBit165)
  %prevMaskBit1Impl66 = icmp ule i1 %4, %3
  call void @llvm.assume(i1 %prevMaskBit1Impl66)
  %prevMaskBit1Impl67 = icmp ule i1 %4, %2
  call void @llvm.assume(i1 %prevMaskBit1Impl67)
  %NonEoFImplMaskBit168 = icmp ne i2 %5, 0
  call void @llvm.assume(i1 %NonEoFImplMaskBit168)
  %6 = icmp eq i4 %.mask52, -1
  %NonEoFImplMaskAll169 = or i1 %.eof51, %6
  call void @llvm.assume(i1 %NonEoFImplMaskAll169)
  %7 = xor i1 %1, true
  %8 = and i1 %.eof51, %7
  %9 = icmp eq i3 %.mask, -1
  %NonEoFImplMaskAll1 = or i1 %.eof51, %9
  %prevMaskBit1Impl38 = icmp ule i1 %4, %1
  %10 = xor i1 %3, true
  %11 = and i1 %.eof51, %10
  %12 = xor i1 %4, true
  %13 = and i1 %.eof51, %12
  %.017 = and i1 %1, %11
  %.023 = and i1 %3, %13
  %.029 = and i1 %4, %.eof51
  %14 = xor i1 %8, true
  %15 = xor i1 %11, true
  %16 = xor i1 %13, true
  %17 = icmp ne i2 %0, -1
  %18 = and i1 %.eof51, %17
  %19 = xor i1 %18, true
  %phi0 = and i1 %19, %4
  %impCache2 = icmp ule i1 %.029, %16
  call void @llvm.assume(i1 %impCache2)
  %phi1 = and i1 %19, %.029
  %phi2 = and i1 %14, %3
  %impCache5 = icmp ule i1 %.023, %15
  call void @llvm.assume(i1 %impCache5)
  %phi3 = and i1 %14, %.023
  %impCache8 = icmp ule i1 %.017, %14
  call void @llvm.assume(i1 %impCache8)
  br i1 %8, label %bb.sink, label %bb.1

bb.1:                                             ; preds = %bb.0
  call void @llvm.assume(i1 %NonEoFImplMaskAll1)
  call void @llvm.assume(i1 %prevMaskBit1Impl38)
  br label %bb.sink

bb.sink:                                          ; preds = %bb.1, %bb.0
  store volatile i1 %phi0, ptr addrspace(2) %out, align 1
  store volatile i1 %phi1, ptr addrspace(2) %out, align 1
  store volatile i1 %phi2, ptr addrspace(2) %out, align 1
  store volatile i1 %phi3, ptr addrspace(2) %out, align 1
  store volatile i1 %1, ptr addrspace(2) %out, align 1
  store volatile i1 %.017, ptr addrspace(2) %out, align 1
  store volatile i1 %.eof51, ptr addrspace(2) %out, align 1
  ret void
}
