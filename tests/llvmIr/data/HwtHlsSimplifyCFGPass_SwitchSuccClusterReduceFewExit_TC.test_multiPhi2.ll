define void @test_multiPhi2(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %0 = load volatile i38, ptr addrspace(1) %i, align 8
  %1 = trunc i38 %0 to i1
  %2 = trunc i38 %0 to i1
  %3 = trunc i38 %0 to i16
  br i1 %2, label %bb32, label %bb44

bb32:                                             ; preds = %bb27
  br label %bb44

bb37:                                             ; preds = %bb44
  br label %bb45

bb44:                                             ; preds = %bb32, %bb27
  %.sink.0lane = phi i3 [ -4, %bb32 ], [ 0, %bb27 ]
  %4 = icmp eq i16 %3, 3
  %5 = icmp eq i16 %3, 4
  %6 = or i1 %4, %5
  %7 = xor i1 %6, true
  %fewExitSw.sucSel.en.bb33.bb37 = or i1 false, %7
  %fewExitSw.sucSel.en.bb33.bb43 = icmp eq i16 %3, 4
  %br.bb43.enFor.bb45 = and i1 %fewExitSw.sucSel.en.bb33.bb43, true
  %fewExitSw.sucSel.en.bb33.bb45 = icmp eq i16 %3, 3
  %.not = xor i1 %1, true
  %fewExitSw.sucSel.en.bb33.bb37.not = xor i1 %fewExitSw.sucSel.en.bb33.bb37, true
  %brmerge = or i1 %.not, %fewExitSw.sucSel.en.bb33.bb37.not
  %.mux = select i1 %.not, i1 false, i1 %fewExitSw.sucSel.en.bb33.bb37
  %fewExitSw.sucSel.en.bb44.bb31 = icmp eq i3 %.sink.0lane, 0
  %8 = xor i1 %brmerge, true
  %br.bb31.enFor.bb37 = and i1 %fewExitSw.sucSel.en.bb44.bb31, %8
  %fewExitSw.sucSel.en.bb44.bb37 = icmp eq i3 %.sink.0lane, 2
  %9 = select i1 %fewExitSw.sucSel.en.bb44.bb37, i1 false, i1 %fewExitSw.sucSel.en.bb33.bb37
  %10 = or i1 %br.bb31.enFor.bb37, %fewExitSw.sucSel.en.bb44.bb37
  %br.bb31.enFor.bb45 = and i1 %fewExitSw.sucSel.en.bb44.bb31, %brmerge
  %11 = icmp eq i3 %.sink.0lane, 1
  %12 = icmp eq i3 %.sink.0lane, 3
  %13 = icmp eq i3 %.sink.0lane, -4
  %14 = or i1 %11, %12
  %fewExitSw.sucSel.en.bb44.bb45 = or i1 %14, %13
  %15 = select i1 %fewExitSw.sucSel.en.bb44.bb45, i1 false, i1 %.mux
  br i1 %10, label %bb37, label %bb45

bb45:                                             ; preds = %bb44, %bb37
  %16 = phi i1 [ %15, %bb44 ], [ %9, %bb37 ]
  br label %bb27
}
