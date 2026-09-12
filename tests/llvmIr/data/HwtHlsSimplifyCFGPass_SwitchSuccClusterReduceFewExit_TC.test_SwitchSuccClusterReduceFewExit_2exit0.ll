define void @test_SwitchSuccClusterReduceFewExit_2exit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %st = alloca i2, align 1
  br label %bb1.sink.split

bb1.sink.split:                                   ; preds = %bb0, %bb7.e1
  %v3.sink = phi i2 [ %v3, %bb7.e1 ], [ 0, %bb0 ]
  store i2 %v3.sink, ptr %st, align 1
  %0 = load volatile i10, ptr addrspace(1) %i, align 2
  %c1 = load volatile i1, ptr addrspace(1) %i, align 2
  %v0 = load volatile i8, ptr addrspace(1) %i, align 2
  %v1 = load volatile i8, ptr addrspace(1) %i, align 2
  %c2 = icmp eq i8 %v0, 2
  %1 = xor i1 %c2, true
  %fewExitSw.sucSel.en.bb1.bb2 = icmp eq i2 %v3.sink, 0
  %br.bb2.enFor.bb4 = and i1 %fewExitSw.sucSel.en.bb1.bb2, %c1
  %br.bb4.enFor.bb5 = and i1 %br.bb2.enFor.bb4, %c2
  %br.bb4.enFor.bb6.e0 = and i1 %br.bb2.enFor.bb4, %1
  %fewExitSw.sucSel.en.bb1.bb6.e0 = icmp eq i2 %v3.sink, 1
  %v2 = select i1 %fewExitSw.sucSel.en.bb1.bb6.e0, i8 %v1, i8 %v0
  %2 = or i1 %br.bb4.enFor.bb6.e0, %fewExitSw.sucSel.en.bb1.bb6.e0
  %3 = zext i1 %br.bb4.enFor.bb5 to i2
  br i1 %2, label %bb6.e0, label %bb7.e1

bb6.e0:                                           ; preds = %bb1.sink.split
  store volatile i8 %v2, ptr addrspace(2) %o, align 1
  br label %bb7.e1

bb7.e1:                                           ; preds = %bb6.e0, %bb1.sink.split
  %v3 = phi i2 [ 0, %bb6.e0 ], [ %3, %bb1.sink.split ]
  br label %bb1.sink.split
}
