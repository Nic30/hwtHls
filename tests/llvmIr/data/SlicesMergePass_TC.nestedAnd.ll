define void @nestedAnd(ptr addrspace(1) %i, ptr addrspace(2) %o) {
  %r0 = load volatile i3, ptr addrspace(1) %i, align 4
  %r1 = load volatile i3, ptr addrspace(1) %i, align 4
  %r2 = load volatile i3, ptr addrspace(1) %i, align 4
  %1 = and i3 %r0, %r1
  %2 = and i3 %1, %r2
  store volatile i3 %2, ptr addrspace(2) %o, align 1
  ret void
}
