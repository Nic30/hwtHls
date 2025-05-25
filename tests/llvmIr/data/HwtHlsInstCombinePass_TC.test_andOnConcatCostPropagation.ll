define void @test_andOnConcatCostPropagation(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %r0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %r1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %c0 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %r0) #1
  %c1 = call i2 @hwtHls.bitConcat.i1.i1(i1 %r1, i1 true) #1
  %and0 = and i2 %c0, %c1
  store volatile i2 %and0, ptr addrspace(2) %dataOut, align 2
  ret void
}
