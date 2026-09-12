define void @test_2exits_and_header_and_exit01phis(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb.header

bb.header:                                        ; preds = %bb.e1, %bb0
  %state = phi i3 [ %state.sink, %bb.e1 ], [ 0, %bb0 ]
  %d0 = load volatile i18, ptr addrspace(1) %i, align 4
  %s0 = load volatile i3, ptr addrspace(1) %i, align 4
  %s1 = load volatile i3, ptr addrspace(1) %i, align 4
  %s2 = load volatile i3, ptr addrspace(1) %i, align 4
  %s3 = load volatile i3, ptr addrspace(1) %i, align 4
  %s4 = load volatile i3, ptr addrspace(1) %i, align 4
  %fewExitSw.sucSel.en.bb.header.bb3 = icmp eq i3 %state, 0
  %fewExitSw.sucSel.en.bb.header.bb4 = icmp eq i3 %state, 2
  %fewExitSw.sucSel.en.bb.header.bb2.noE0 = icmp eq i3 %state, -4
  %br.bb4.enFor.bb.e0 = and i1 %fewExitSw.sucSel.en.bb.header.bb4, true
  %fewExitSw.sucSel.en.bb.header.bb.e0 = icmp eq i3 %state, 3
  %state.0 = select i1 %fewExitSw.sucSel.en.bb.header.bb.e0, i3 %s0, i3 %s1
  %0 = or i1 %br.bb4.enFor.bb.e0, %fewExitSw.sucSel.en.bb.header.bb.e0
  %br.bb2.noE0.enFor.bb.e1 = and i1 %fewExitSw.sucSel.en.bb.header.bb2.noE0, true
  %br.bb3.enFor.bb.e1 = and i1 %fewExitSw.sucSel.en.bb.header.bb3, true
  %fewExitSw.sucSel.en.bb.header.bb.e1 = icmp eq i3 %state, 1
  %1 = select i1 %br.bb3.enFor.bb.e1, i3 %s2, i3 %s3
  %2 = select i1 %fewExitSw.sucSel.en.bb.header.bb.e1, i3 %s4, i3 %1
  br i1 %0, label %bb.e0, label %bb.e1

bb.e0:                                            ; preds = %bb.header
  store volatile i32 0, ptr addrspace(2) %o, align 4
  %c0 = load volatile i1, ptr addrspace(1) %i, align 4
  br i1 %c0, label %bb.e1, label %bb2

bb2:                                              ; preds = %bb.e0
  br label %bb.e1

bb.e1:                                            ; preds = %bb.header, %bb2, %bb.e0
  %state.sink = phi i3 [ %2, %bb.header ], [ %s3, %bb2 ], [ %state.0, %bb.e0 ]
  br label %bb.header
}
