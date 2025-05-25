define void @test_nothingToPrune(ptr addrspace(1) %o) {
entry:
  br label %body

body:                                             ; preds = %body, %entry
  %.phiConc = phi i8 [ 0, %entry ], [ %.selConc, %body ]
  %0 = call i3 @hwtHls.bitRangeGet.i8.i4.i3.5(i8 %.phiConc, i4 5) #1
  %1 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.4(i8 %.phiConc, i4 4) #1
  %2 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8 %.phiConc, i4 0) #1
  store volatile i8 %.phiConc, ptr addrspace(1) %o, align 1
  %"5" = add i8 %.phiConc, 1
  %3 = call i8 @hwtHls.bitConcat.i4.i1.i3(i4 %2, i1 true, i3 %0) #1
  %.selConc = select i1 %1, i8 %3, i8 %"5"
  br label %body
}
