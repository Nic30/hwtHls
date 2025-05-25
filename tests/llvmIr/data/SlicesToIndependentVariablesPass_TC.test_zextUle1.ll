define void @test_zextUle1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
BB0:
  %r0 = load volatile i3, ptr addrspace(1) %i, align 1
  %r1 = load volatile i3, ptr addrspace(1) %i, align 1
  %0 = call i5 @hwtHls.bitConcat.i2.i3(i2 0, i3 %r1) #1
  %1 = zext i3 %r0 to i5
  %ule = icmp ule i5 %0, %1
  store volatile i1 %ule, ptr addrspace(2) %o, align 1
  ret void
}
