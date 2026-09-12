define void @test_multiPhi4(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %bb3.ioFsmStBefore.IoFsmSt = alloca i3, align 1
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %i_read1.r0.data.reg2mem.2.reg2mem.0 = phi i16 [ %i_read1.r0.data.reg2mem.3.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %0 = load i3, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %1 = load volatile i38, ptr addrspace(1) %i, align 8
  %2 = trunc i38 %1 to i1
  %3 = trunc i38 %1 to i16
  %4 = trunc i16 %i_read1.r0.data.reg2mem.2.reg2mem.0 to i3
  %fewExitSw.sucSel.en.bb27.bb30 = icmp eq i3 %0, 0
  %fewExitSw.sucSel.en.bb27.bb40 = icmp eq i3 %0, 2
  %br.bb40.enFor.bb34 = and i1 %fewExitSw.sucSel.en.bb27.bb40, true
  %fewExitSw.sucSel.en.bb27.bb34 = icmp eq i3 %0, 3
  %5 = or i1 %br.bb40.enFor.bb34, %fewExitSw.sucSel.en.bb27.bb34
  %br.bb34.enFor.bb38 = and i1 %5, true
  %fewExitSw.sucSel.en.bb27.bb38 = icmp eq i3 %0, -4
  %6 = or i1 %br.bb34.enFor.bb38, %fewExitSw.sucSel.en.bb27.bb38
  %br.bb30.enFor.bb44 = and i1 %fewExitSw.sucSel.en.bb27.bb30, true
  %br.bb38.enFor.bb44 = and i1 %6, true
  %fewExitSw.sucSel.en.bb27.bb44 = icmp eq i3 %0, 1
  %7 = select i1 %br.bb38.enFor.bb44, i3 0, i3 0
  %.sink.0lane = select i1 %fewExitSw.sucSel.en.bb27.bb44, i3 %4, i3 %7
  store i3 %.sink.0lane, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %8 = icmp eq i16 %3, 3
  %9 = icmp eq i16 %3, 4
  %10 = or i1 %8, %9
  %11 = xor i1 %10, true
  %fewExitSw.sucSel.en.bb33.bb37 = or i1 false, %11
  %12 = icmp eq i16 %3, 3
  %13 = icmp eq i16 %3, 4
  %fewExitSw.sucSel.en.bb33.bb45 = or i1 %12, %13
  %br.bb37.enFor.bb45 = and i1 %fewExitSw.sucSel.en.bb33.bb37, true
  %14 = select i1 %br.bb37.enFor.bb45, i16 %3, i16 0
  br i1 %2, label %bb33, label %bb45

bb33:                                             ; preds = %bb27
  br label %bb45

bb45:                                             ; preds = %bb33, %bb27
  %i_read1.r0.data.reg2mem.3.ph.1lane = phi i16 [ %14, %bb33 ], [ 0, %bb27 ]
  br label %bb27
}
