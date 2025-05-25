define void @parallelSelect4(ptr addrspace(1) %i0, ptr addrspace(2) %o0, ptr addrspace(2) %o1, ptr addrspace(2) %o2, ptr addrspace(2) %o3) {
  %i00 = load volatile i4, ptr addrspace(1) %i0, align 1
  %c = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #1
  %1 = xor i4 %i00, -1
  %2 = select i1 %c, i4 %1, i4 -3
  %xor0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %2, i3 0) #1
  %xor1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %2, i3 1) #1
  %xor2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.2(i4 %2, i3 2) #1
  %xor3 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %2, i3 3) #1
  store volatile i1 %xor0, ptr addrspace(2) %o0, align 1
  store volatile i1 %xor1, ptr addrspace(2) %o1, align 1
  store volatile i1 %xor2, ptr addrspace(2) %o2, align 1
  store volatile i1 %xor3, ptr addrspace(2) %o3, align 1
  ret void
}
