define void @test_tryReducePopcnt_toCTLZ(ptr addrspace(1) %condIn, ptr addrspace(2) %dataOut) {
bb.0:
  %c0 = load volatile i1, ptr addrspace(1) %condIn, align 1
  %c1.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
  %c2.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
  %c3.0 = load volatile i1, ptr addrspace(1) %condIn, align 1
  %c1 = and i1 %c0, %c1.0
  %c2 = and i1 %c1, %c2.0
  %c3 = and i1 %c2, %c3.0
  %c = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 %c0, i1 %c1, i1 %c2, i1 %c3) #3
  %impCache = icmp ule i1 %c1, %c0
  call void @llvm.assume(i1 %impCache)
  %impCache1 = icmp ule i1 %c2, %c1
  call void @llvm.assume(i1 %impCache1)
  %impCache2 = icmp ule i1 %c3, %c2
  call void @llvm.assume(i1 %impCache2)
  %res = call i4 @llvm.cttz.i4(i4 %c, i1 false)
  store volatile i4 %res, ptr addrspace(2) %dataOut, align 2
  ret void
}
