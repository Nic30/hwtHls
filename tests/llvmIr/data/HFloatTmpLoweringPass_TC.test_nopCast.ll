define void @test_nopCast(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %r0 = load volatile i5, ptr addrspace(1) %dataIn, align 1
  store volatile i5 %r0, ptr addrspace(2) %dataOut, align 2
  ret void
}
