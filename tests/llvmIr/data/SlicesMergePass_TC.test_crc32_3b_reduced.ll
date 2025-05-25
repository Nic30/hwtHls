define void @test_crc32_3b_reduced(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
  %"dataIn0(dataIn_read)" = load volatile i3, ptr addrspace(1) %dataIn, align 1
  %"0" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %"dataIn0(dataIn_read)", i3 0) #1
  %"1" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %"dataIn0(dataIn_read)", i3 1) #1
  %"2" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %"dataIn0(dataIn_read)", i3 2) #1
  %"3" = xor i1 %"2", %"1"
  %"4" = and i1 %"0", %"3"
  %"5" = xor i1 %"4", true
  %"6" = call i2 @hwtHls.bitConcat.i1.i1(i1 %"3", i1 %"5") #1
  store volatile i2 %"6", ptr addrspace(2) %dataOut, align 4
  ret void
}
