define void @test_phiDoubleTrunc0(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
bb0:
  %0 = load volatile i3, ptr addrspace(1) %data_in, align 4
  %r0 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %0, i3 0) #1
  br label %bb3

bb3:                                              ; preds = %bb3, %bb0
  %it.01 = phi i1 [ %r0, %bb0 ], [ false, %bb3 ]
  store volatile i1 %it.01, ptr addrspace(2) %data_out, align 2
  br label %bb3
}
