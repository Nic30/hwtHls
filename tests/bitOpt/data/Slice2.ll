define void @mainThread(i1 addrspace(1)* %i0, i5 addrspace(2)* %i1, i2 addrspace(3)* %o) {
mainThread:
  br label %block0

block0:                                           ; preds = %mainThread
  %i00 = load volatile i1, i1 addrspace(1)* %i0, align 1
  %i11 = load volatile i5, i5 addrspace(2)* %i1, align 1
  %0 = call i2 @hwtHls.bitConcat.i1.i1(i1 %i00, i1 false)
  store volatile i2 %0, i2 addrspace(3)* %o, align 1
  ret void
}
