define void @test_tryReduceSelectInst_toAndOr1(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %v0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  %v0.bit0 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.0(i8 %v0, i4 0) #1
  %v1 = load volatile i3, ptr addrspace(1) %dataIn, align 1
  %c = icmp eq i3 %v1, -1
  %0 = call i8 @hwtHls.bitConcat.i7.i1(i7 0, i1 %v0.bit0) #1
  %res = select i1 %c, i8 %0, i8 %v0
  store volatile i8 %res, ptr addrspace(2) %dataOut, align 1
  ret void
}
