define void @loadMerge(ptr addrspace(1) %i, ptr addrspace(2) %o) {
loadMerge:
  br label %bb0_sw

bb0_sw_def:                                       ; preds = %bb0_sw
  %i1.w0 = load volatile i17, ptr addrspace(1) %i, align 4
  %0 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i1.w0, i6 0) #1
  %1 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i1.w0, i6 16) #1
  %i1.w1 = load volatile i17, ptr addrspace(1) %i, align 4
  %2 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %i1.w1, i6 16) #1
  %3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i1.w1, i6 0) #1
  %4 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %i1.w1, i6 0) #1
  %i1 = call i25 @hwtHls.bitConcat.i16.i8.i1(i16 %0, i8 %4, i1 %1) #1
  %5 = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %i1, i6 0) #1
  %6 = zext i24 %5 to i32
  %7 = or i1 %1, %2
  %i3 = call i33 @hwtHls.bitConcat.i16.i16.i1(i16 %0, i16 %3, i1 %7) #1
  %8 = call i32 @hwtHls.bitRangeGet.i33.i7.i32.0(i33 %i3, i7 0) #1
  %9 = icmp eq i16 %12, 4
  %10 = or i1 %9, %1
  %11 = select i1 %9, i32 %8, i32 %6
  store volatile i32 %11, ptr addrspace(2) %o, align 4
  br i1 %10, label %bb_opt_ld, label %bb0_sw

bb0_sw:                                           ; preds = %bb0_sw_def, %bb_opt_ld, %loadMerge
  %i0.w0 = load volatile i17, ptr addrspace(1) %i, align 4
  %12 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %i0.w0, i6 0) #1
  %.off = add i16 %12, -3
  %switch = icmp ult i16 %.off, 2
  br i1 %switch, label %bb0_sw_def, label %bb_opt_ld

bb_opt_ld:                                        ; preds = %bb0_sw, %bb0_sw_def
  %i3.opt = load volatile i17, ptr addrspace(1) %i, align 4
  br label %bb0_sw
}
