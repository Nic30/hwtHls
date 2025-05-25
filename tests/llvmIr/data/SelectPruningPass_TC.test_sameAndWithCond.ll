define void @test_sameAndWithCond(ptr addrspace(1) %c, ptr addrspace(2) %v0a, ptr addrspace(3) %v1a, ptr addrspace(4) %v2a, ptr addrspace(5) %o) {
entry:
  br label %body

body:                                             ; preds = %entry
  %c0 = load volatile i1, ptr addrspace(1) %c, align 1
  %v0 = load volatile i1, ptr addrspace(2) %v0a, align 1
  %v1 = load volatile i1, ptr addrspace(3) %v1a, align 1
  %v2 = load volatile i1, ptr addrspace(4) %v2a, align 1
  %s0.v0 = and i1 %v1, %v0
  %s0 = select i1 %c0, i1 %s0.v0, i1 false
  store volatile i1 %s0, ptr addrspace(5) %o, align 1
  ret void
}
