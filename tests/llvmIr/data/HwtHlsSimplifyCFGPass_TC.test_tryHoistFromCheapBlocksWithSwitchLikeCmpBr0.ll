define void @test_tryHoistFromCheapBlocksWithSwitchLikeCmpBr0(ptr addrspace(1) %o) {
bb0:
  br label %bb.c0

bb.c0:                                            ; preds = %bb.exit, %bb0
  %i = phi i4 [ 0, %bb0 ], [ %i.be, %bb.exit ]
  %0 = icmp eq i4 %i, 4
  %1 = zext i4 %i to i8
  br i1 %0, label %bb.def, label %bb.c1

bb.c1:                                            ; preds = %bb.c0
  store volatile i8 %1, ptr addrspace(1) %o, align 1
  %2 = add nuw i4 %i, 1
  %hwrange.continue10.not = icmp eq i4 %i, 7
  br i1 %hwrange.continue10.not, label %bb.def, label %bb.exit

bb.exit:                                          ; preds = %bb.def, %bb.c1
  %i.be = phi i4 [ 0, %bb.def ], [ %2, %bb.c1 ]
  br label %bb.c0

bb.def:                                           ; preds = %bb.c1, %bb.c0
  br label %bb.exit
}
