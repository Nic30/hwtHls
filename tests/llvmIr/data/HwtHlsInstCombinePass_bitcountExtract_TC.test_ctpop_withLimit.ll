define void @test_ctpop_withLimit(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %acc = phi i8 [ 0, %bb0 ], [ %6, %bb1 ]
  %0 = load volatile i4, ptr addrspace(1) %rx, align 1
  %1 = call i4 @llvm.ctpop.i4(i4 %0)
  %2 = zext i4 %1 to i9
  %3 = zext i8 %acc to i9
  %4 = add i9 %3, %2
  %5 = call i9 @llvm.umin.i9(i9 %4, i9 10)
  %6 = trunc i9 %5 to i8
  store volatile i8 %6, ptr addrspace(2) %tx, align 1
  br label %bb1
}
