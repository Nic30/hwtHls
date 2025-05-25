define void @test_nestedSelWithSameCond0(ptr addrspace(1) %c, ptr addrspace(2) %v1, ptr addrspace(3) %o) {
entry:
  br label %body

body:                                             ; preds = %entry
  %c0 = load volatile i1, ptr addrspace(1) %c, align 1
  %s0.v1 = load volatile i2, ptr addrspace(2) %v1, align 1
  %s1.v1.1 = load volatile i1, ptr addrspace(1) %c, align 1
  %0 = call i4 @hwtHls.bitConcat.i2.i1.i1(i2 %s0.v1, i1 true, i1 %s1.v1.1) #1
  %s1 = select i1 %c0, i4 -6, i4 %0
  store volatile i4 %s1, ptr addrspace(3) %o, align 1
  ret void
}
