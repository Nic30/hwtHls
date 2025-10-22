define void @test_addSub(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %r0 = load volatile i5, ptr addrspace(1) %dataIn, align 1
  %res0.01 = call i5 @hwtHls.fp.fsub.i5(i5 4, i5 %r0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #1
  %res1.02 = call i5 @hwtHls.fp.fadd.i5(i5 %r0, i5 -4, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #1
  store volatile i5 %res0.01, ptr addrspace(2) %dataOut, align 2
  store volatile i5 %res1.02, ptr addrspace(2) %dataOut, align 2
  ret void
}
