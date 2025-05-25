define void @test_tryReduceZExt_onZExt(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %v0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %v0.1 = zext i1 %v0 to i9
  store volatile i9 %v0.1, ptr addrspace(2) %dataOut, align 2
  ret void
}
