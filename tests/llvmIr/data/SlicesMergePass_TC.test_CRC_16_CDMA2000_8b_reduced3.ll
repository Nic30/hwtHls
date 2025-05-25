define void @test_CRC_16_CDMA2000_8b_reduced3(ptr addrspace(1) %dataOut) {
bb0:
  store volatile i2 0, ptr addrspace(1) %dataOut, align 2
  ret void
}
