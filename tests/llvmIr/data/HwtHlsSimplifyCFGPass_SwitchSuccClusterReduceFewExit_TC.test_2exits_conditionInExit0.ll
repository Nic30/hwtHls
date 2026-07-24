define void @test_2exits_conditionInExit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb.latch, %bb0
  %swCond = phi i3 [ %swCond.phi, %bb.latch ], [ 0, %bb0 ]
  %c0 = load volatile i3, ptr addrspace(1) %i, align 4
  %c1 = load volatile i3, ptr addrspace(1) %i, align 4
  %c2 = icmp eq i3 %c1, 0
  %fewExitSw.sucSel.en.bb1.bb.c0 = icmp eq i3 %c0, 0
  %fewExitSw.sucSel.en.bb1.bb.c2 = icmp eq i3 %c0, 2
  %fewExitSw.sucSel.en.bb1.bb.c3 = icmp eq i3 %c0, 3
  %br.bb.c0.enFor.bb.latch = and i1 %fewExitSw.sucSel.en.bb1.bb.c0, true
  %fewExitSw.sucSel.en.bb1.bb.latch = icmp eq i3 %c0, 1
  %0 = xor i1 %fewExitSw.sucSel.en.bb1.bb.c2, true
  %1 = xor i1 %fewExitSw.sucSel.en.bb1.bb.c2, true
  %2 = xor i1 %fewExitSw.sucSel.en.bb1.bb.c2, true
  %3 = xor i1 %fewExitSw.sucSel.en.bb1.bb.c2, true
  %4 = xor i1 %fewExitSw.sucSel.en.bb1.bb.c2, true
  br i1 %fewExitSw.sucSel.en.bb1.bb.c2, label %bb.c2, label %bb.latch

bb.c2:                                            ; preds = %bb1
  store volatile i32 10, ptr addrspace(2) %o, align 4
  br i1 %c2, label %bb.latch, label %bb.c3

bb.c3:                                            ; preds = %bb.c2
  br label %bb.latch

bb.latch:                                         ; preds = %bb1, %bb.c3, %bb.c2
  %5 = phi i3 [ poison, %bb1 ], [ 0, %bb.c3 ], [ 3, %bb.c2 ]
  %6 = select i1 %fewExitSw.sucSel.en.bb1.bb.latch, i3 2, i3 %c0
  %swCond.phi = select i1 %fewExitSw.sucSel.en.bb1.bb.c2, i3 %5, i3 %6
  store volatile i3 %swCond.phi, ptr addrspace(2) %o, align 4
  br label %bb1
}
