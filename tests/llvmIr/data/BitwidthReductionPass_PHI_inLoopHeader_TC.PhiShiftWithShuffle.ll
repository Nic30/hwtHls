define void @PhiShiftWithShuffle(ptr addrspace(1) %din, ptr addrspace(2) %dout) {
bb0:
  %din_read = load volatile i32, ptr addrspace(1) %din, align 4
  br label %bbHeader

bbHeader:                                         ; preds = %bbHeader, %bb0
  %shiftPhi = phi i128 [ 21528975894082904090066538856997790465, %bb0 ], [ %shiftPhi.1, %bbHeader ]
  %shiftPhi.32to96 = call i64 @hwtHls.bitRangeGet.i128.i8.i64.32(i128 %shiftPhi, i8 32) #1
  %shiftPhi.32to64 = call i32 @hwtHls.bitRangeGet.i128.i8.i32.32(i128 %shiftPhi, i8 32) #1
  %shiftPhi.96to128 = call i32 @hwtHls.bitRangeGet.i128.i8.i32.96(i128 %shiftPhi, i8 96) #1
  %shiftPhi.add = add i32 %din_read, %shiftPhi.32to64
  %0 = call i128 @hwtHls.bitConcat.i32.i32.i64(i32 %shiftPhi.96to128, i32 %shiftPhi.add, i64 %shiftPhi.32to96) #1
  store volatile i128 %0, ptr addrspace(2) %dout, align 4
  %shiftPhi.1 = call i128 @hwtHls.bitConcat.i32.i32.i64(i32 %shiftPhi.96to128, i32 %shiftPhi.add, i64 %shiftPhi.32to96) #1
  br label %bbHeader
}
