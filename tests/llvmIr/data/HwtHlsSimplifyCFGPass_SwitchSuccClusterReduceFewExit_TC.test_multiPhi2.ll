define void @test_multiPhi2(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %0 = load volatile i38, ptr addrspace(1) %i, align 8
  %1 = trunc i38 %0 to i1
  %2 = trunc i38 %0 to i1
  %3 = trunc i38 %0 to i16
  br i1 %2, label %bb32, label %bb45

bb32:                                             ; preds = %bb27
  br label %bb45

bb45:                                             ; preds = %bb27, %bb32
  %.sink.0lane = phi i3 [ 0, %bb27 ], [ -4, %bb32 ]
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
  %br.bb31.enFor.bb371 = and i1 %fewExitSw.sucSel.en.bb44.bb31, %8
  %9 = icmp eq i3 %.sink.0lane, 1
  %10 = icmp eq i3 %.sink.0lane, 2
  %11 = icmp eq i3 %.sink.0lane, 3
  %12 = icmp eq i3 %.sink.0lane, -4
  %13 = or i1 %9, %10
  %14 = or i1 %13, %11
  %fewExitSw.sucSel.en.bb44.bb45 = or i1 %14, %12
  %br.bb371.enFor.bb45 = and i1 %br.bb31.enFor.bb371, true
  %br.bb31.enFor.bb45 = and i1 %fewExitSw.sucSel.en.bb44.bb31, %brmerge
  %15 = select i1 %br.bb371.enFor.bb45, i1 %fewExitSw.sucSel.en.bb33.bb37, i1 false
  %16 = select i1 %br.bb31.enFor.bb45, i1 %.mux, i1 %15
  br label %bb27
}
