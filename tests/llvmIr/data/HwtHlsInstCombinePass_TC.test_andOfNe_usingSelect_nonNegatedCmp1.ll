define void @test_andOfNe_usingSelect_nonNegatedCmp1(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
bb.0:
  %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
  %cmp0.n = icmp ne i9 %v0, 128
  %0 = xor i1 %cmp0.n, true
  %cmp2.n = icmp ne i9 %v0, 124
  %impCache = icmp ule i1 %0, %cmp2.n
  call void @llvm.assume(i1 %impCache)
  store volatile i1 %cmp2.n, ptr addrspace(3) %dataOut, align 2
  ret void
}
