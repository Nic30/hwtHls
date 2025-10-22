define void @test_tryReduceSelectInst_concatWithConst0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
bb.0:
  %c0 = load volatile i1, ptr addrspace(2) %condIn, align 1
  %c1 = load volatile i1, ptr addrspace(2) %condIn, align 1
  %v0 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %c0) #1
  %v1 = select i1 %c1, i2 0, i2 %v0
  store volatile i2 %v1, ptr addrspace(3) %dataOut, align 2
  ret void
}
