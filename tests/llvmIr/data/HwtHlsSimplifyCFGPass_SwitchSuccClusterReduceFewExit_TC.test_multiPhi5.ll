define void @test_multiPhi5(ptr addrspace(1) %i, ptr addrspace(2) %o) {
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
  %5 = trunc i3 %0 to i1
  %.sink.0lane = select i1 %5, i3 %4, i3 0
  store i3 %.sink.0lane, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %6 = icmp eq i16 %3, 3
  %7 = icmp eq i16 %3, 4
  %8 = or i1 %6, %7
  %9 = xor i1 %8, true
  %fewExitSw.sucSel.en.bb33.bb37 = or i1 false, %9
  %br.bb37.enFor.bb45 = and i1 %fewExitSw.sucSel.en.bb33.bb37, true
  %10 = icmp eq i16 %3, 3
  %11 = icmp eq i16 %3, 4
  %fewExitSw.sucSel.en.bb33.bb45 = or i1 %10, %11
  %12 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i16 0, i16 %3
  br i1 %2, label %bb33, label %bb45

bb33:                                             ; preds = %bb27
  br label %bb45

bb45:                                             ; preds = %bb33, %bb27
  %i_read1.r0.data.reg2mem.3.ph.1lane = phi i16 [ %12, %bb33 ], [ 0, %bb27 ]
  br label %bb27
}
