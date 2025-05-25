define void @test_andOfNe_usingSelect_nonNegatedCmp1(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
bb.0:
  %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
  %cmp2.n = icmp ne i9 %v0, 124
  store volatile i1 %cmp2.n, ptr addrspace(3) %dataOut, align 2
  ret void
}
