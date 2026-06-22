define void @test_SwitchSuccClusterReduceFewExit_0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb.entry:
  br label %bb.loop0.head

bb.loop0.head.BB0Split:                           ; preds = %bb.loop0.head, %bb.loop1.head
  br label %bb.loop0.head

bb.loop0.head:                                    ; preds = %bb.loop0.head.BB0Split, %bb.entry
  %e0 = load volatile i1, ptr addrspace(1) %i, align 4
  %c0 = load volatile i2, ptr addrspace(1) %i, align 4
  %fewExitSw.sucSel.en.bb.loop0.head.bb.swJump1 = icmp eq i2 %c0, 1
  %fewExitSw.sucSel.en.bb.loop0.head.bb.swJump2 = icmp eq i2 %c0, -2
  %0 = xor i1 %e0, true
  %fewExitSw.sucSel.en.bb.loop0.head.bb.swJump0 = icmp eq i2 %c0, 0
  %1 = or i1 %fewExitSw.sucSel.en.bb.loop0.head.bb.swJump2, %fewExitSw.sucSel.en.bb.loop0.head.bb.swJump1
  %2 = and i1 %0, %1
  %3 = or i1 %2, %fewExitSw.sucSel.en.bb.loop0.head.bb.swJump0
  br i1 %3, label %bb.loop1.head, label %bb.loop0.head.BB0Split

bb.loop1.head:                                    ; preds = %bb.loop0.head, %bb.loop1.head
  %e1 = load volatile i1, ptr addrspace(1) %i, align 4
  br i1 %e1, label %bb.loop0.head.BB0Split, label %bb.loop1.head
}
