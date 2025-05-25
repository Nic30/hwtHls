define void @test_constFold_Select(ptr addrspace(1) %i0, ptr addrspace(1) %i1, ptr addrspace(2) %o0, ptr addrspace(2) %o1) {
  %i00 = load volatile i8, ptr addrspace(1) %i0, align 1
  %c = call i1 @hwtHls.bitRangeGet.i8.i64.i1.0(i8 %i00, i64 0) #1
  %i10 = load volatile i8, ptr addrspace(1) %i1, align 1
  %1 = select i1 %c, i8 %i00, i8 %i10
  %"4" = call i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8 %1, i4 0) #1
  %"5" = call i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8 %1, i4 4) #1
  %"6" = select i1 %c, i4 3, i4 0
  store volatile i4 %"4", ptr addrspace(2) %o0, align 1
  store volatile i4 %"5", ptr addrspace(2) %o1, align 1
  store volatile i4 %"6", ptr addrspace(2) %o1, align 1
  ret void
}
