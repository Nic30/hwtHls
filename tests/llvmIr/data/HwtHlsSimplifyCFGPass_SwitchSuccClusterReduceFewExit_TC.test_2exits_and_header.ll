define void @test_2exits_and_header(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb3

bb3.BB0Split:                                     ; preds = %bb5.e1, %bb3.sw, %bb3
  br label %bb3

bb3:                                              ; preds = %bb3.BB0Split, %bb0
  %c0 = load volatile i1, ptr addrspace(1) %i, align 8
  %v0 = load volatile i16, ptr addrspace(1) %i, align 8
  br i1 %c0, label %bb3.sw, label %bb3.BB0Split

bb3.sw:                                           ; preds = %bb3
  %0 = icmp eq i16 %v0, 2
  %1 = icmp eq i16 %v0, 4
  %2 = or i1 %0, %1
  %3 = xor i1 %2, true
  %fewExitSw.sucSel.en.bb3.sw.bb9 = or i1 false, %3
  %fewExitSw.sucSel.en.bb3.sw.bb4 = icmp eq i16 %v0, 2
  %br.bb4.enFor.bb5.e1 = and i1 %fewExitSw.sucSel.en.bb3.sw.bb4, true
  %fewExitSw.sucSel.en.bb3.sw.bb5.e1 = icmp eq i16 %v0, 4
  %phi0 = select i1 %fewExitSw.sucSel.en.bb3.sw.bb5.e1, i16 %v0, i16 0
  %4 = or i1 %br.bb4.enFor.bb5.e1, %fewExitSw.sucSel.en.bb3.sw.bb5.e1
  %br.bb9.enFor.bb5 = and i1 %fewExitSw.sucSel.en.bb3.sw.bb9, true
  br i1 %4, label %bb5.e1, label %bb3.BB0Split

bb5.e1:                                           ; preds = %bb3.sw
  store volatile i16 %phi0, ptr addrspace(2) %o, align 4
  br label %bb3.BB0Split
}
