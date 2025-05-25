define void @test_tryReduceSelectInst_deepAdderChainToBitCounts0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
bb.0:
  %v0 = load volatile i9, ptr addrspace(1) %dataIn, align 1
  %c0 = load volatile i1, ptr addrspace(2) %condIn, align 1
  %c1 = load volatile i1, ptr addrspace(2) %condIn, align 1
  %c2 = load volatile i1, ptr addrspace(2) %condIn, align 1
  %c3 = load volatile i1, ptr addrspace(2) %condIn, align 1
  %0 = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 %c0, i1 %c1, i1 %c2, i1 %c3) #2
  %1 = xor i4 %0, -1
  %2 = call i4 @llvm.ctpop.i4(i4 %1)
  %3 = zext i4 %2 to i9
  %v8 = add i9 %v0, %3
  store volatile i9 %v8, ptr addrspace(3) %dataOut, align 2
  ret void
}
