define void @mainThread(i16* %i, i32 addrspace(1)* %o) {
mainThread:
  %i0 = load volatile i16, i16* %i, align 2
  %0 = call i32 @hwtHls.bitConcat.i16.i16(i16 %i0, i16 0)
  store volatile i32 %0, i32 addrspace(1)* %o, align 4
  ret void
}
