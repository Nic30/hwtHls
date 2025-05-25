define void @test_ctpop_withLimit_and_iremovableIntermediateUse(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %acc = phi i8 [ 0, %bb0 ], [ %12, %bb1 ]
  %0 = load volatile i4, ptr addrspace(1) %rx, align 1
  %1 = call i3 @hwtHls.bitRangeGet.i4.i3.i3.0(i4 %0, i3 0) #2
  %2 = call i3 @llvm.ctpop.i3(i3 %1)
  %3 = zext i3 %2 to i9
  %4 = zext i8 %acc to i9
  %5 = add i9 %4, %3
  %6 = call i9 @llvm.umin.i9(i9 %5, i9 10)
  %7 = trunc i9 %6 to i8
  %8 = call i4 @llvm.ctpop.i4(i4 %0)
  %9 = zext i4 %8 to i9
  %10 = add i9 %4, %9
  %11 = call i9 @llvm.umin.i9(i9 %10, i9 10)
  %12 = trunc i9 %11 to i8
  %c.3.intermediate = icmp ne i8 %7, 5
  store volatile i8 %12, ptr addrspace(2) %tx, align 1
  store volatile i1 %c.3.intermediate, ptr addrspace(2) %tx, align 1
  br label %bb1
}
