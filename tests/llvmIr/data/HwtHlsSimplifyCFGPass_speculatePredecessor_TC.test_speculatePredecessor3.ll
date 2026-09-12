define void @test_speculatePredecessor3(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb27

bb27:                                             ; preds = %bb44, %bb0
  %i_read3.r0.eof.reg2mem.0.reg2mem.0 = phi i1 [ false, %bb44 ], [ undef, %bb0 ]
  %0 = load volatile i38, ptr addrspace(1) %i, align 8
  %1 = trunc i38 %0 to i1
  %2 = trunc i38 %0 to i16
  br i1 %1, label %bb32, label %bb44

bb32:                                             ; preds = %bb27
  br label %bb44

bb44:                                             ; preds = %bb32, %bb27
  %.sink.0lane = phi i3 [ -4, %bb32 ], [ 0, %bb27 ]
  %cond = icmp eq i16 %2, 4
  %fewExitSw.sucSel.en.bb44.bb31 = icmp eq i3 %.sink.0lane, 0
  %br.bb31.enFor.bb33 = and i1 %fewExitSw.sucSel.en.bb44.bb31, %1
  %br.bb33.enFor.bb45 = and i1 %br.bb31.enFor.bb33, true
  %3 = icmp eq i3 %.sink.0lane, 1
  %4 = icmp eq i3 %.sink.0lane, 2
  %5 = icmp eq i3 %.sink.0lane, 3
  %6 = icmp eq i3 %.sink.0lane, -4
  %7 = or i1 %3, %4
  %8 = or i1 %7, %5
  %fewExitSw.sucSel.en.bb44.bb45 = or i1 %8, %6
  %9 = xor i1 %1, true
  %br.bb31.enFor.bb45 = and i1 %fewExitSw.sucSel.en.bb44.bb31, %9
  %10 = or i1 %br.bb33.enFor.bb45, %fewExitSw.sucSel.en.bb44.bb45
  %11 = or i1 %10, %br.bb31.enFor.bb45
  %br.bb45.enFor.bb27 = and i1 %11, true
  br label %bb27
}
