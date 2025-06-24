define void @loadMerge(ptr addrspace(1) %i, ptr addrspace(2) %o) {
loadMerge:
  br label %bb0_sw

bb0_sw:                                           ; preds = %bb0_sw_case3, %bb_opt_ld, %loadMerge
  %i0.w0 = load volatile i17, ptr addrspace(1) %i, align 4
  %0 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i0.w0, i6 0) #1
  switch i16 %0, label %bb_opt_ld [
    i16 3, label %bb0_sw_case3
    i16 4, label %bb0_sw_case4
  ]

bb0_sw_case3:                                     ; preds = %bb0_sw
  %i1.w0 = load volatile i17, ptr addrspace(1) %i, align 4
  %1 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i1.w0, i6 0) #1
  %2 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i1.w0, i6 16) #1
  %i1.w1 = load volatile i17, ptr addrspace(1) %i, align 4
  %3 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %i1.w1, i6 0) #1
  %i1 = call i25 @hwtHls.bitConcat.i16.i8.i1(i16 %1, i8 %3, i1 %2) #1
  %4 = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %i1, i6 0) #1
  %5 = zext i24 %4 to i32
  store volatile i32 %5, ptr addrspace(2) %o, align 4
  br i1 %2, label %bb_opt_ld, label %bb0_sw

bb_opt_ld:                                        ; preds = %bb0_sw, %bb0_sw_case4, %bb0_sw_case3
  %i3.opt = load volatile i17, ptr addrspace(1) %i, align 4
  br label %bb0_sw

bb0_sw_case4:                                     ; preds = %bb0_sw
  %i2.w0 = load volatile i17, ptr addrspace(1) %i, align 4
  %6 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i2.w0, i6 0) #1
  %7 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i2.w0, i6 16) #1
  %i2.w1 = load volatile i17, ptr addrspace(1) %i, align 4
  %8 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i2.w1, i6 0) #1
  %9 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i2.w1, i6 16) #1
  %10 = or i1 %7, %9
  %i3 = call i33 @hwtHls.bitConcat.i16.i16.i1(i16 %6, i16 %8, i1 %10) #1
  %11 = call i32 @hwtHls.bitRangeGet.i33.i7.i32.0(i33 %i3, i7 0) #1
  store volatile i32 %11, ptr addrspace(2) %o, align 4
  br label %bb_opt_ld
}
