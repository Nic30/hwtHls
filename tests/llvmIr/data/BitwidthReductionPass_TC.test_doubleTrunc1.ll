define void @test_doubleTrunc1(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) {
bb0:
  br label %bb3

bb3:                                              ; preds = %bb3, %bb0
  %r0 = load volatile i3, ptr addrspace(1) %data_in, align 4
  %0 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %r0, i3 0) #1
  %c = load volatile i1, ptr addrspace(1) %data_in, align 4
  %it.01 = select i1 %c, i1 %0, i1 false
  store volatile i1 %it.01, ptr addrspace(2) %data_out, align 2
  br label %bb3
}
