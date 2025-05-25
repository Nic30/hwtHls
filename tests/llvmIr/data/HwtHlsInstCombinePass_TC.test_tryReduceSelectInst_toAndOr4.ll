define void @test_tryReduceSelectInst_toAndOr4(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %v0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %v1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %0 = xor i1 %v1, true
  %1 = or i1 %0, %v0
  %res = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %1) #1
  store volatile i2 %res, ptr addrspace(2) %dataOut, align 1
  ret void
}
