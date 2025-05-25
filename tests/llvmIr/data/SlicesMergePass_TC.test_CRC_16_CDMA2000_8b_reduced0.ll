define void @test_CRC_16_CDMA2000_8b_reduced0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb0:
  %dataIn_read = load volatile i8, ptr addrspace(1) %dataIn, align 1
  store volatile i16 0, ptr addrspace(2) %dataOut, align 2
  ret void
}
