define void @test_nonBB0DominatedExit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb.entry:
  br label %bb.loop0.head

bb.loop0.head.ExitLatch:                          ; preds = %bb.sw, %bb.loop1.head
  br label %bb.loop0.head

bb.loop0.head:                                    ; preds = %bb.loop0.head.ExitLatch, %bb.entry
  %e0 = load volatile i1, ptr addrspace(1) %i, align 4
  %c0 = load volatile i2, ptr addrspace(1) %i, align 4
  %c1 = load volatile i1, ptr addrspace(1) %i, align 4
  br i1 %c1, label %bb.sw, label %bb.loop1.head

bb.sw:                                            ; preds = %bb.loop0.head
  %fewExitSw.sucSel.en.bb.sw.bb.swJump1 = icmp eq i2 %c0, 1
  %fewExitSw.sucSel.en.bb.sw.bb.swJump2 = icmp eq i2 %c0, -2
  %0 = xor i1 %e0, true
  %fewExitSw.sucSel.en.bb.sw.bb.swJump0 = icmp eq i2 %c0, 0
  %1 = or i1 %fewExitSw.sucSel.en.bb.sw.bb.swJump2, %fewExitSw.sucSel.en.bb.sw.bb.swJump1
  %2 = and i1 %0, %1
  %3 = or i1 %2, %fewExitSw.sucSel.en.bb.sw.bb.swJump0
  br i1 %3, label %bb.loop1.head, label %bb.loop0.head.ExitLatch

bb.loop1.head:                                    ; preds = %bb.sw, %bb.loop1.head, %bb.loop0.head
  %e1 = load volatile i1, ptr addrspace(1) %i, align 4
  br i1 %e1, label %bb.loop0.head.ExitLatch, label %bb.loop1.head
}
