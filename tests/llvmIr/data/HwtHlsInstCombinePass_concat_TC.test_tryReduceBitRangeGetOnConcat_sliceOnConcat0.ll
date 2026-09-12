define void @test_tryReduceBitRangeGetOnConcat_sliceOnConcat0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
bb.0:
  %v0 = load volatile i8, ptr addrspace(2) %condIn, align 1
  %v1 = load volatile i8, ptr addrspace(2) %condIn, align 1
  %v2 = load volatile i1, ptr addrspace(2) %condIn, align 1
  %v4 = call i16 @hwtHls.bitConcat.i8.i8(i8 %v0, i8 %v1) #1
  store volatile i16 %v4, ptr addrspace(3) %dataOut, align 2
  ret void
}
