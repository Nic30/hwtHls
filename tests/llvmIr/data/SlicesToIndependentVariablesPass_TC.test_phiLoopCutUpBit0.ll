define void @test_phiLoopCutUpBit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
BB0:
  %r = load volatile i8, ptr addrspace(1) %i, align 1
  %0 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.7(i8 %r, i4 7) #1
  %1 = call i7 @hwtHls.bitRangeGet.i8.i4.i7.0(i8 %r, i4 0) #1
  br label %BB1

BB1:                                              ; preds = %BB1, %BB0
  %phi1 = phi i7 [ %1, %BB0 ], [ %phi1, %BB1 ]
  %phi2 = phi i1 [ %0, %BB0 ], [ false, %BB1 ]
  %2 = call i8 @hwtHls.bitConcat.i7.i1(i7 %phi1, i1 %phi2) #1
  store volatile i8 %2, ptr addrspace(2) %o, align 4
  br label %BB1
}
