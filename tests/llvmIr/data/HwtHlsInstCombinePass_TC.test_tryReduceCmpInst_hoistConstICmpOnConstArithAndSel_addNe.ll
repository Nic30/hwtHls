define void @test_tryReduceCmpInst_hoistConstICmpOnConstArithAndSel_addNe(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %r0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  %r0_p1 = add i8 %r0, 1
  %res = icmp ne i8 %r0_p1, 10
  store volatile i1 %res, ptr addrspace(2) %dataOut, align 2
  ret void
}
