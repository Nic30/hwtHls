define void @test_ctpop_0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %acc = phi i8 [ 0, %bb0 ], [ %acc.3, %bb1 ]
  %0 = load volatile i4, ptr addrspace(1) %rx, align 1
  %1 = call i4 @llvm.ctpop.i4(i4 %0)
  %2 = zext i4 %1 to i8
  %acc.3 = add i8 %acc, %2
  store volatile i8 %acc.3, ptr addrspace(2) %tx, align 1
  br label %bb1
}
