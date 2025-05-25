define void @test_phiLoop0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
BB0:
  %r = load volatile i8, ptr addrspace(1) %i, align 1
  br label %BB1

BB1:                                              ; preds = %BB1, %BB0
  %phi = phi i8 [ %r, %BB0 ], [ %xor, %BB1 ]
  %and = and i8 %phi, -2
  %xor = xor i8 %and, -1
  store volatile i8 %xor, ptr addrspace(2) %o, align 4
  br label %BB1
}
