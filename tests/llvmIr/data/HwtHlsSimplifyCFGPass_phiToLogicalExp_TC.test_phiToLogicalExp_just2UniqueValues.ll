define void @test_phiToLogicalExp_just2UniqueValues(ptr addrspace(1) %cIn, ptr addrspace(2) %o) {
bb0:
  br label %bb.L1.head

bb.L1.head:                                       ; preds = %bb0, %bb.L0.latch, %bb.L1.head
  %c0 = load volatile i1, ptr addrspace(1) %cIn, align 1
  %c1 = load volatile i1, ptr addrspace(1) %cIn, align 1
  %c2 = load volatile i1, ptr addrspace(1) %cIn, align 1
  %c3 = load volatile i1, ptr addrspace(1) %cIn, align 1
  %v0 = load volatile i32, ptr addrspace(1) %cIn, align 1
  %v1 = load volatile i32, ptr addrspace(1) %cIn, align 1
  %brmerge = or i1 %c0, %c1
  %brmerge1 = or i1 %brmerge, %c2
  %v0.mux = select i1 %brmerge, i32 %v0, i32 %v1
  %brmerge2 = or i1 %brmerge1, %c3
  %v0.mux.mux = select i1 %brmerge1, i32 %v0.mux, i32 %v1
  br i1 %brmerge2, label %bb.L0.latch, label %bb.L1.head

bb.L0.latch:                                      ; preds = %bb.L1.head
  store volatile i32 %v0.mux.mux, ptr addrspace(2) %o, align 4
  br label %bb.L1.head
}
