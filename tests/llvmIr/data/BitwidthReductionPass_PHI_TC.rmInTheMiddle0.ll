define void @rmInTheMiddle0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
BB0:
  br label %BB1

BB1:                                              ; preds = %BB0
  %rxRaw = load volatile i19, ptr addrspace(1) %rx, align 4
  %rxFinalRaw = call i8 @hwtHls.bitRangeGet.i19.i6.i8.0(i19 %rxRaw, i6 0) #1
  %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw, i6 18) #1
  br i1 %rxLast, label %BBv0, label %BBv1

BBv0:                                             ; preds = %BB1
  br label %BBend

BBv1:                                             ; preds = %BB1
  br label %BBend

BBend:                                            ; preds = %BBv1, %BBv0
  store volatile i8 %rxFinalRaw, ptr addrspace(2) %tx, align 4
  ret void
}
