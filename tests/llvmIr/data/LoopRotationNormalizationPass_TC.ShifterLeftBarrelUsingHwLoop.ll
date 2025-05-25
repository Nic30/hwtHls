define void @ShifterLeftBarrelUsingHwLoop(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %sh) {
entry:
  br label %bb0

bb0:                                              ; preds = %bb2, %entry
  %i0 = load volatile i2, ptr addrspace(1) %i, align 1
  %sh1 = load volatile i1, ptr addrspace(3) %sh, align 1
  %"2" = icmp ne i1 %sh1, false
  br i1 %"2", label %bb1.preheader, label %bb2

bb1.preheader:                                    ; preds = %bb0
  br label %bb1

bb1:                                              ; preds = %bb1.preheader, %bb1
  %v.3 = phi i2 [ %1, %bb1 ], [ %i0, %bb1.preheader ]
  %0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %v.3, i2 0) #1
  %1 = call i2 @hwtHls.bitConcat.i1.i1(i1 false, i1 %0) #1
  %"7" = icmp ne i1 %sh1, false
  br i1 %"7", label %bb1, label %bb2.loopexit

bb2.loopexit:                                     ; preds = %bb1
  %.lcssa = phi i2 [ %1, %bb1 ]
  br label %bb2

bb2:                                              ; preds = %bb2.loopexit, %bb0
  %v.9 = phi i2 [ %i0, %bb0 ], [ %.lcssa, %bb2.loopexit ]
  store volatile i2 %v.9, ptr addrspace(2) %o, align 1
  br label %bb0
}
