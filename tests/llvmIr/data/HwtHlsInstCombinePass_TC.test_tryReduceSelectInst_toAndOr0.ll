define void @test_tryReduceSelectInst_toAndOr0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %v0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
  store volatile i1 true, ptr addrspace(2) %dataOut, align 2
  ret void
}
