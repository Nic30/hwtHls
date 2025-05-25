define void @test_tryReduceSelectInst_toAndOr3(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %v0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %v1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %0 = xor i1 %v0, true
  %s0 = or i1 %0, %v1
  %s1 = and i1 %v0, %v1
  store volatile i1 %s0, ptr addrspace(2) %dataOut, align 1
  store volatile i1 %s1, ptr addrspace(2) %dataOut, align 1
  ret void
}
