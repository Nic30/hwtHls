define void @mainThread(i32 addrspace(1)* %i, i32 addrspace(2)* %o) {
mainThread:
  %i0 = load volatile i32, i32 addrspace(1)* %i, align 4
  %"4" = add i32 %i0, 1
  %0 = call i16 @hwtHls.bitRangeGet.i32.i64.i16.16(i32 %"4", i64 16)
  %1 = call i16 @hwtHls.bitRangeGet.i32.i64.i16.0(i32 %"4", i64 0)
  %2 = xor i16 %1, -1
  %3 = xor i16 %0, -1
  %4 = call i32 @hwtHls.bitConcat.i16.i16(i16 %2, i16 %3)
  store volatile i32 %4, i32 addrspace(2)* %o, align 4
  ret void
}
