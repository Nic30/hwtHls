define void @test_cmpUleLowerBits0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %a = load volatile i5, ptr addrspace(1) %dataIn, align 32
  %c1 = icmp ule i5 %a, 0
  store volatile i1 %c1, ptr addrspace(2) %dataOut, align 32
  br label %bb1
}
