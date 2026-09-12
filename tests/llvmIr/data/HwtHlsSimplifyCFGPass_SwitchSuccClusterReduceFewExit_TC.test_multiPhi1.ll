define void @test_multiPhi1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb27

bb27:                                             ; preds = %bb27, %bb0
  %0 = load volatile i38, ptr addrspace(1) %i, align 8
  br label %bb27
}
