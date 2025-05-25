define void @test_ctpop_toCtto(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  %0 = load volatile i8, ptr addrspace(1) %rx, align 1
  %strb = call i3 @hwtHls.bitRangeGet.i8.i4.i3.0(i8 %0, i4 0) #3
  %strb0 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.0(i8 %0, i4 0) #3
  %strb1 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.1(i8 %0, i4 1) #3
  %strb2 = call i1 @hwtHls.bitRangeGet.i8.i4.i1.2(i8 %0, i4 2) #3
  %prevMaskBit1Impl.0 = icmp ule i1 %strb1, %strb0
  call void @llvm.assume(i1 %prevMaskBit1Impl.0)
  %prevMaskBit1Impl.1 = icmp ule i1 %strb2, %strb1
  call void @llvm.assume(i1 %prevMaskBit1Impl.1)
  %1 = xor i3 %strb, -1
  %ct = call i3 @llvm.cttz.i3(i3 %1, i1 false)
  store volatile i3 %ct, ptr addrspace(2) %tx, align 1
  ret void
}
