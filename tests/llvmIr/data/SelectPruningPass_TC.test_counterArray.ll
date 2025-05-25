define void @test_counterArray(ptr addrspace(1) %i) {
entry:
  br label %body

body:                                             ; preds = %body, %entry
  %v0 = phi i16 [ 0, %entry ], [ %v0.1, %body ]
  %v1 = phi i16 [ 0, %entry ], [ %v1.1, %body ]
  %v2 = phi i16 [ 0, %entry ], [ %v2.1, %body ]
  %v3 = phi i16 [ 0, %entry ], [ %v3.1, %body ]
  %i_addr = load volatile i2, ptr addrspace(1) %i, align 1
  %i_addr_0 = icmp eq i2 %i_addr, 0
  %i_addr_1 = icmp eq i2 %i_addr, 1
  %i_addr_2 = icmp eq i2 %i_addr, -2
  %i_addr_3 = icmp eq i2 %i_addr, -1
  %inSel0 = select i1 %i_addr_0, i16 %v0, i16 %v3
  %inSel1 = select i1 %i_addr_1, i16 %v1, i16 %inSel0
  %inSel2 = select i1 %i_addr_2, i16 %v2, i16 %inSel1
  %v.incr = add i16 %inSel2, 1
  %v0.1 = select i1 %i_addr_0, i16 %v.incr, i16 %v0
  %v1.1 = select i1 %i_addr_1, i16 %v.incr, i16 %v1
  %v2.1 = select i1 %i_addr_2, i16 %v.incr, i16 %v2
  %v3.1 = select i1 %i_addr_3, i16 %v.incr, i16 %v3
  br label %body
}
