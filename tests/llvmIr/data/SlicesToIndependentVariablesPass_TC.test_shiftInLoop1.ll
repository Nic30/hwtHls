define void @test_shiftInLoop1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
BB0:
  %r = load volatile i4, ptr addrspace(1) %i, align 1
  %0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %r, i3 3) #1
  %1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.2(i4 %r, i3 2) #1
  %2 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %r, i3 1) #1
  br label %BB1

BB1:                                              ; preds = %BB1, %BB0
  %phi1 = phi i1 [ %2, %BB0 ], [ %phi2, %BB1 ]
  %phi2 = phi i1 [ %1, %BB0 ], [ %phi3, %BB1 ]
  %phi3 = phi i1 [ %0, %BB0 ], [ false, %BB1 ]
  %3 = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 %phi1, i1 %phi2, i1 %phi3, i1 false) #1
  store volatile i4 %3, ptr addrspace(2) %o, align 1
  br label %BB1
}
