define void @test_andOfNe_usingSelect(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
bb.0:
  %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
  %c2 = icmp eq i9 %v0, 6
  store volatile i1 %c2, ptr addrspace(3) %dataOut, align 2
  ret void
}
