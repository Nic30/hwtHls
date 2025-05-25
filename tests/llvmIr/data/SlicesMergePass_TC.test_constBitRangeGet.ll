define void @test_constBitRangeGet(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb0:
  %dataIn_read = load volatile i8, ptr addrspace(1) %dataIn, align 1
  store volatile i1 false, ptr addrspace(2) %dataOut, align 2
  store volatile i2 0, ptr addrspace(2) %dataOut, align 2
  ret void
}
