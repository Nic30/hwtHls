define void @test_tryReduceConcatOnConcat(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %r0 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %r1 = load volatile i1, ptr addrspace(1) %dataIn, align 1
  %c1 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 true, i1 %r0, i1 %r1) #1
  store volatile i3 %c1, ptr addrspace(2) %dataOut, align 2
  ret void
}
