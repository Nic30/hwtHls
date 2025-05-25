define void @multilevelXorNestedInConcat(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %r0 = load volatile i1, ptr addrspace(1) %i, align 1
  %r1 = load volatile i1, ptr addrspace(1) %i, align 1
  %w0 = xor i1 %r0, true
  %w = call i2 @hwtHls.bitConcat.i1.i1(i1 %w0, i1 %r0) #1
  store volatile i2 %w, ptr addrspace(2) %o, align 8
  ret void
}
