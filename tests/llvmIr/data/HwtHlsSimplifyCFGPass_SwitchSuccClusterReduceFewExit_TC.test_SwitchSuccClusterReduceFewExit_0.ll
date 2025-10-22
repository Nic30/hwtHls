define void @test_SwitchSuccClusterReduceFewExit_0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb.entry:
  br label %bb.loop0.head

bb.loop0.head:                                    ; preds = %bb.loop0.head, %bb.loop1.head, %bb.entry
  %e0 = load volatile i1, ptr addrspace(1) %i, align 4
  %c0 = load volatile i2, ptr addrspace(1) %i, align 4
  %0 = icmp eq i2 %c0, 0
  %1 = icmp eq i2 %c0, 1
  %2 = xor i1 %e0, true
  %3 = select i1 %1, i1 %2, i1 %0
  %4 = icmp eq i2 %c0, -2
  %5 = select i1 %4, i1 %2, i1 %3
  br i1 %5, label %bb.loop1.head, label %bb.loop0.head

bb.loop1.head:                                    ; preds = %bb.loop0.head, %bb.loop1.head
  %e1 = load volatile i1, ptr addrspace(1) %i, align 4
  br i1 %e1, label %bb.loop0.head, label %bb.loop1.head
}
