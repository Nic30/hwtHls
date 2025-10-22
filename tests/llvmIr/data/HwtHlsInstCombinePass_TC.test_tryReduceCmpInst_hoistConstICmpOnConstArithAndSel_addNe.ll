define void @test_tryReduceCmpInst_hoistConstICmpOnConstArithAndSel_addNe(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %r0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  %res1 = icmp ne i8 %r0, 9
  store volatile i1 %res1, ptr addrspace(2) %dataOut, align 2
  ret void
}
