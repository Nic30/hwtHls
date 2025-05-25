define void @test_andOfNe_usingSelect_0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
bb.0:
  %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
  %cmp.eq124 = icmp eq i9 %v0, 124
  %cmp.eq125 = icmp eq i9 %v0, 125
  %cmp.eq124_or_125 = or i1 %cmp.eq125, %cmp.eq124
  store volatile i1 %cmp.eq124_or_125, ptr addrspace(3) %dataOut, align 1
  ret void
}
