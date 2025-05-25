define void @test_parallelMultipletimes(ptr addrspace(1) %i0, ptr addrspace(1) %i1, ptr addrspace(2) %o0, ptr addrspace(2) %o1) {
  %i00 = load volatile i2, ptr addrspace(1) %i0, align 1
  %i10 = load volatile i2, ptr addrspace(1) %i1, align 1
  %1 = xor i2 %i00, %i10
  %xor0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %1, i2 0) #1
  %xor1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %1, i2 1) #1
  %2 = and i2 %i00, %i10
  %and0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %2, i2 0) #1
  %and1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %2, i2 1) #1
  %and2 = and i1 %and0, %and1
  %xor2 = xor i1 %xor0, %xor1
  store volatile i1 %xor2, ptr addrspace(2) %o0, align 1
  store volatile i1 %and2, ptr addrspace(2) %o1, align 1
  ret void
}
