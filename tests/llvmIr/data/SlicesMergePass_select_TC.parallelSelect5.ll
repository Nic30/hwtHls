define void @parallelSelect5(ptr addrspace(1) %i0, ptr addrspace(2) %o0, ptr addrspace(2) %o1, ptr addrspace(2) %o2, ptr addrspace(2) %o3) {
  %i00 = load volatile i4, ptr addrspace(1) %i0, align 1
  %c = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i00, i64 0) #1
  %1 = select i1 %c, i4 6, i4 -8
  %sel0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.0(i4 %1, i3 0) #1
  %sel3 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %1, i3 1) #1
  %sel2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.2(i4 %1, i3 2) #1
  %sel1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %1, i3 3) #1
  store volatile i1 %sel0, ptr addrspace(2) %o0, align 1
  store volatile i1 %sel1, ptr addrspace(2) %o1, align 1
  store volatile i1 %sel2, ptr addrspace(2) %o2, align 1
  store volatile i1 %sel3, ptr addrspace(2) %o3, align 1
  ret void
}
