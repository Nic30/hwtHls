define void @test_nonBB0DominatedExit0_phiInE1UsingE0Phi(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb.entry:
  br label %bb.loop0.head

bb.loop0.head.ExitLatch:                          ; preds = %bb.sw, %bb.loop1.head
  %phiE0.ph = phi i2 [ %5, %bb.sw ], [ -1, %bb.loop1.head ]
  br label %bb.loop0.head

bb.loop0.head:                                    ; preds = %bb.loop0.head.ExitLatch, %bb.entry
  %phiE0 = phi i2 [ 0, %bb.entry ], [ %phiE0.ph, %bb.loop0.head.ExitLatch ]
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
  %br.bb.swJump2.enFor.bb.loop0.head.ExitLatch = and i1 %fewExitSw.sucSel.en.bb.sw.bb.swJump2, %e0
  %4 = xor i1 %br.bb.swJump2.enFor.bb.loop0.head.ExitLatch, true
  %5 = call i2 @hwtHls.bitConcat.i1.i1(i1 %4, i1 %br.bb.swJump2.enFor.bb.loop0.head.ExitLatch) #1
  br i1 %3, label %bb.loop1.head, label %bb.loop0.head.ExitLatch

bb.loop1.head:                                    ; preds = %bb.sw, %bb.loop1.head, %bb.loop0.head
  %phiE1 = phi i2 [ 1, %bb.sw ], [ -2, %bb.loop1.head ], [ %phiE0, %bb.loop0.head ]
  store volatile i2 %phiE1, ptr addrspace(2) %o, align 1
  %e1 = load volatile i1, ptr addrspace(1) %i, align 4
  br i1 %e1, label %bb.loop0.head.ExitLatch, label %bb.loop1.head
}
