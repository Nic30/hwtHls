define void @mainThread(i16 addrspace(1)* %i, i32 addrspace(2)* %o) {
mainThread:
  %i0 = load volatile i16, i16 addrspace(1)* %i, align 2
  %0 = call i32 @hwtHls.bitConcat.i16.i16(i16 %i0, i16 0)
  store volatile i32 %0, i32 addrspace(2)* %o, align 4
  ret void
}
