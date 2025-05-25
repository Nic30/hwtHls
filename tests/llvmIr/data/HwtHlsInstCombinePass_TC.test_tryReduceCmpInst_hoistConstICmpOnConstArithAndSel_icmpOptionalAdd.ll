define void @test_tryReduceCmpInst_hoistConstICmpOnConstArithAndSel_icmpOptionalAdd(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
bb.0:
  %r0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  %c = load volatile i1, ptr addrspace(2) %condIn, align 1
  %r0_p1 = add i8 %r0, 1
  %r1 = select i1 %c, i8 %r0, i8 %r0_p1
  %res = icmp ne i8 %r1, 1
  store volatile i1 %res, ptr addrspace(3) %dataOut, align 2
  ret void
}
