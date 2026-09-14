define void @test_requiresNewBBForPhis(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb2

bb2:                                              ; preds = %bb7, %bb0
  %c.phi = phi i3 [ %c.phi.latch, %bb7 ], [ 0, %bb0 ]
  %0 = load volatile i18, ptr addrspace(1) %i, align 4
  %fewExitSw.sucSel.en.bb2.bb5.unswitch = icmp eq i3 %c.phi, 0
  %1 = call i3 @hwtHls.bitConcat.i2.i1(i2 0, i1 %fewExitSw.sucSel.en.bb2.bb5.unswitch) #1
  switch i3 %c.phi, label %bb7 [
    i3 3, label %bb4
    i3 2, label %bb4
  ]

bb4:                                              ; preds = %bb2, %bb2
  store volatile i32 0, ptr addrspace(2) %o, align 4
  br label %bb7

bb7:                                              ; preds = %bb2, %bb4
  %c.phi.latch = phi i3 [ 0, %bb4 ], [ %1, %bb2 ]
  br label %bb2
}
