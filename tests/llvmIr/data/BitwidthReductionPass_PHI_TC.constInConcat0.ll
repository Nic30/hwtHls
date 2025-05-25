define void @constInConcat0(ptr addrspace(1) %rx, ptr addrspace(2) %txBody) {
bb0:
  %rxRaw0 = load volatile i19, ptr addrspace(1) %rx, align 4
  %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw0, i6 18) #1
  %rxData0to8 = call i8 @hwtHls.bitRangeGet.i19.i6.i8.0(i19 %rxRaw0, i6 0) #1
  br i1 %rxLast, label %bb1, label %bb2

bb1:                                              ; preds = %bb0
  br label %bb3

bb2:                                              ; preds = %bb0
  br label %bb3

bb3:                                              ; preds = %bb2, %bb1
  %rxRawFinal1 = phi i1 [ false, %bb1 ], [ true, %bb2 ]
  %0 = call i19 @hwtHls.bitConcat.i8.i9.i1.i1(i8 %rxData0to8, i9 -256, i1 %rxRawFinal1, i1 true) #1
  store volatile i19 %0, ptr addrspace(2) %txBody, align 4
  ret void
}
