define void @test_tryReduceBitRangeGetOnConcat0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %r0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  %r1 = load volatile i2, ptr addrspace(1) %dataIn, align 1
  %v3 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %r1, i2 1) #1
  store volatile i1 %v3, ptr addrspace(2) %dataOut, align 2
  ret void
}
