define void @test_phiToLogicalExp0(ptr addrspace(1) %cIn, ptr addrspace(2) %out) {
bb.entry:
  %bb0.g.c = load volatile i1, ptr addrspace(1) %cIn, align 1
  %bb0.e.c = load volatile i1, ptr addrspace(1) %cIn, align 1
  %bb1.g.c = load volatile i1, ptr addrspace(1) %cIn, align 1
  %bb1.e.c = load volatile i1, ptr addrspace(1) %cIn, align 1
  %bb2.g.c = load volatile i1, ptr addrspace(1) %cIn, align 1
  %bb2.e.c = load volatile i1, ptr addrspace(1) %cIn, align 1
  %0 = xor i1 %bb1.e.c, true
  %spec.select3 = and i1 %0, %bb2.g.c
  %1 = xor i1 %bb0.e.c, true
  %spec.select = and i1 %1, %bb1.g.c
  %2 = xor i1 %bb0.e.c, true
  %spec.select4 = and i1 %2, %spec.select3
  store volatile i1 %bb0.g.c, ptr addrspace(2) %out, align 1
  store volatile i1 %spec.select, ptr addrspace(2) %out, align 1
  store volatile i1 %spec.select4, ptr addrspace(2) %out, align 1
  ret void
}
