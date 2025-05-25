define void @test_phiDoubleTrunc1(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
bb0:
  br label %bb3

bb3:                                              ; preds = %bb3, %bb0
  %it.01 = phi i1 [ poison, %bb0 ], [ false, %bb3 ]
  store volatile i1 %it.01, ptr addrspace(2) %data_out, align 2
  br label %bb3
}
