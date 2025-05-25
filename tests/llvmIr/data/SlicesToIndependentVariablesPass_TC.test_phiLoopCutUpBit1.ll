define void @test_phiLoopCutUpBit1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
BB0:
  %r = load volatile i8, ptr addrspace(1) %i, align 1
  %0 = call i7 @hwtHls.bitRangeGet.i8.i4.i7.0(i8 %r, i4 0) #1
  br label %BB1

BB1:                                              ; preds = %BB1, %BB0
  %phi1 = phi i7 [ %0, %BB0 ], [ %phi1, %BB1 ]
  %1 = zext i7 %phi1 to i8
  store volatile i8 %1, ptr addrspace(2) %o, align 4
  br label %BB1
}
