define void @constInConcat1(ptr addrspace(1) %rx, ptr addrspace(2) %txBody) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb0
  %rxRaw0 = load volatile i19, ptr addrspace(1) %rx, align 4
  %rxData0to16 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %rxRaw0, i6 0) #1
  %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw0, i6 18) #1
  %0 = call i19 @hwtHls.bitConcat.i16.i2.i1(i16 %rxData0to16, i2 1, i1 %rxLast) #1
  store volatile i19 %0, ptr addrspace(2) %txBody, align 4
  ret void
}
