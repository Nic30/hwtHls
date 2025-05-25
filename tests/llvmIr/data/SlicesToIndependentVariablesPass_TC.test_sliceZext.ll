define void @test_sliceZext(ptr addrspace(1) %i, ptr addrspace(2) %o) {
BB0:
  %r = load volatile i25, ptr addrspace(1) %i, align 4
  %rSlice = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %r, i6 0) #1
  %0 = zext i24 %rSlice to i32
  store volatile i32 %0, ptr addrspace(2) %o, align 4
  ret void
}
