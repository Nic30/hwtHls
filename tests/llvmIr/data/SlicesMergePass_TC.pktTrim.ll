define void @pktTrim(ptr %lenIn, ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %len = load volatile i11, ptr %lenIn, align 1
  %r0 = load volatile i1, ptr addrspace(1) %rx, align 1
  %r1 = load volatile i1, ptr addrspace(1) %rx, align 1
  %r2 = load volatile i1, ptr addrspace(1) %rx, align 1
  %r3 = load volatile i1, ptr addrspace(1) %rx, align 1
  %.not = icmp eq i11 %len, -648
  %r1.not = xor i1 %r1, true
  %0 = or i1 %r0, %r1.not
  %1 = or i1 %r2, %r1.not
  %2 = and i1 %0, %1
  %3 = or i1 %r3, %r1.not
  %4 = and i1 %2, %3
  %5 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %0, i1 %2, i1 %4) #1
  %w.opConc = select i1 %.not, i3 0, i3 %5
  store volatile i3 %w.opConc, ptr addrspace(2) %tx, align 8
  br label %bb1
}
