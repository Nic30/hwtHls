define void @test_tryReduceSelectInst_toAndOr5(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %i_read2 = load volatile i16, ptr addrspace(1) %i, align 2
  %0 = icmp eq i16 %i_read2, 10
  %1 = xor i1 %0, true
  %.mux = call i16 @hwtHls.bitConcat.i1.i1.i1.i1.i12(i1 false, i1 %1, i1 %0, i1 %1, i12 1) #1
  store volatile i16 %.mux, ptr addrspace(2) %o, align 2
  ret void
}
