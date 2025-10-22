define void @test_nopCast2xDifferent(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb.0:
  %r0 = load volatile i6, ptr addrspace(1) %dataIn, align 1
  %v1.casted = call i5 @hwtHls.fp.castHFloatTmpToHFloatTmpRaw.i6.i5(i6 %r0, i1 true, i8 3, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #0
  store volatile i5 %v1.casted, ptr addrspace(2) %dataOut, align 2
  ret void
}
