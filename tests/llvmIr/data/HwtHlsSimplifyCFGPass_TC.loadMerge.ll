define void @loadMerge(ptr addrspace(1) %i, ptr addrspace(2) %o) {
loadMerge:
  br label %bb0_sw

bb0_sw_def:                                       ; preds = %bb0_sw
  %i1.w0 = load volatile i17, ptr addrspace(1) %i, align 4
  %0 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i1.w0, i6 0) #1
  %1 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i1.w0, i6 16) #1
  %i1.w1 = load volatile i17, ptr addrspace(1) %i, align 4
  %2 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i1.w1, i6 0) #1
  %3 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %i1.w1, i6 0) #1
  %4 = call i24 @hwtHls.bitConcat.i16.i8(i16 %0, i8 %3) #1
  %5 = zext i24 %4 to i32
  %6 = call i32 @hwtHls.bitConcat.i16.i16(i16 %0, i16 %2) #1
  %fewExitSw.sucSel.en..bb0_sw_case4 = icmp eq i16 %9, 4
  %7 = or i1 %fewExitSw.sucSel.en..bb0_sw_case4, %1
  %8 = select i1 %fewExitSw.sucSel.en..bb0_sw_case4, i32 %6, i32 %5
  store volatile i32 %8, ptr addrspace(2) %o, align 4
  br i1 %7, label %bb_opt_ld, label %bb0_sw

bb0_sw:                                           ; preds = %bb0_sw_def, %bb_opt_ld, %loadMerge
  %i0.w0 = load volatile i17, ptr addrspace(1) %i, align 4
  %9 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i0.w0, i6 0) #1
  %.off = add i16 %9, -3
  %switch = icmp ult i16 %.off, 2
  br i1 %switch, label %bb0_sw_def, label %bb_opt_ld

bb_opt_ld:                                        ; preds = %bb0_sw, %bb0_sw_def
  %i3.opt = load volatile i17, ptr addrspace(1) %i, align 4
  br label %bb0_sw
}
