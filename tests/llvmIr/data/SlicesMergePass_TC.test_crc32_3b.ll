define void @test_crc32_3b(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
  %"dataIn0(dataIn_read)" = load volatile i3, ptr addrspace(1) %dataIn, align 1
  %1 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.1(i3 %"dataIn0(dataIn_read)", i3 1) #1
  %"0" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %"dataIn0(dataIn_read)", i3 0) #1
  %"1" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %"dataIn0(dataIn_read)", i3 1) #1
  %"2" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %"dataIn0(dataIn_read)", i3 2) #1
  %2 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %"2", i1 %"0", i1 %"0") #1
  %3 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %"1", i1 %"1", i1 true) #1
  %"3.opConc1" = xor i3 %2, %3
  %"8" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %"3.opConc1", i3 0) #1
  %"110" = xor i1 %"0", %"8"
  %4 = xor i3 %"dataIn0(dataIn_read)", -1
  %"126" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %4, i3 0) #1
  %"15" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %4, i3 2) #1
  %"26" = call i1 @hwtHls.bitRangeGet.i3.i3.i1.1(i3 %4, i3 1) #1
  %"17" = xor i1 %"1", %"15"
  %"19" = xor i1 %"0", %"17"
  %5 = call i14 @hwtHls.bitConcat.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1.i1(i1 %"8", i1 %"19", i1 %"0", i1 %"0", i1 %"2", i1 %"0", i1 %"0", i1 %"2", i1 %"0", i1 %"0", i1 %"2", i1 %"110", i1 %"0", i1 %"0") #1
  %6 = call i14 @hwtHls.bitConcat.i2.i2.i1.i2.i1.i2.i1.i1.i1.i1(i2 -1, i2 %1, i1 %"1", i2 %1, i1 %"1", i2 %1, i1 %"1", i1 true, i1 %"1", i1 true) #1
  %"3.opConc2" = xor i14 %5, %6
  %"3" = call i32 @hwtHls.bitConcat.i1.i14.i1.i1.i1.i1.i3.i1.i3.i1.i1.i1.i3(i1 %"2", i14 %"3.opConc2", i1 false, i1 %"15", i1 %"26", i1 %"126", i3 0, i1 %"15", i3 %"3.opConc1", i1 %"15", i1 %"26", i1 %"126", i3 0) #1
  store volatile i32 %"3", ptr addrspace(2) %dataOut, align 4
  ret void
}
