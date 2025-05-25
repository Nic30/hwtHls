define void @multilevelXorNestedInConcat1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %r0 = load volatile i1, ptr addrspace(1) %i, align 1
  %r1 = load volatile i1, ptr addrspace(1) %i, align 1
  %r2 = load volatile i1, ptr addrspace(1) %i, align 1
  %r3 = load volatile i1, ptr addrspace(1) %i, align 1
  %r4 = load volatile i1, ptr addrspace(1) %i, align 1
  %r5 = load volatile i1, ptr addrspace(1) %i, align 1
  %0 = call i2 @hwtHls.bitConcat.i1.i1(i1 %r0, i1 %r1) #1
  %1 = call i2 @hwtHls.bitConcat.i1.i1(i1 %r1, i1 %r2) #1
  %w.opConc = xor i2 %0, %1
  %w0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %w.opConc, i2 0) #1
  %w0.1 = xor i1 %w0, %r5
  store volatile i2 %0, ptr addrspace(2) %o, align 8
  %2 = call i2 @hwtHls.bitConcat.i1.i1(i1 %r4, i1 %r3) #1
  %w6.opConc = xor i2 %w.opConc, %2
  store volatile i1 %w0.1, ptr addrspace(2) %o, align 8
  store volatile i2 %w6.opConc, ptr addrspace(2) %o, align 8
  ret void
}
