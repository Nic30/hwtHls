define void @test_tryOrToBitConcat_0(ptr addrspace(1) %o) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %i.0 = phi i3 [ %i.2, %bb1 ], [ 0, %bb0 ]
  %i.1 = zext i3 %i.0 to i64
  %v = call i64 @hwtHls.bitConcat.i3.i61(i3 %i.0, i61 1) #1
  store volatile i64 %v, ptr addrspace(1) %o, align 8
  %i.2 = add i3 %i.0, 1
  br label %bb1
}
