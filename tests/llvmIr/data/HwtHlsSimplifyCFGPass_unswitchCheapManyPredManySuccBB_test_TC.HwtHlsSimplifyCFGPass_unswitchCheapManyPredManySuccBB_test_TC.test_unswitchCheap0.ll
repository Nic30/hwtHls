define void @HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB_test_TC.test_unswitchCheap0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  br label %bb.header

bb.header:                                        ; preds = %bb.latch, %bb0
  %c = load volatile i3, ptr addrspace(1) %i, align 4
  %br.en.2 = load volatile i1, ptr addrspace(1) %i, align 4
  %br.en.3 = load volatile i1, ptr addrspace(1) %i, align 4
  %br.en.5 = load volatile i1, ptr addrspace(1) %i, align 4
  %d.0 = load volatile i8, ptr addrspace(1) %i, align 4
  %d.1 = load volatile i8, ptr addrspace(1) %i, align 4
  %d.5 = load volatile i8, ptr addrspace(1) %i, align 4
  %d.6 = load volatile i8, ptr addrspace(1) %i, align 4
  switch i3 %c, label %bb.caseDef [
    i3 0, label %bb.case0
    i3 1, label %bb.toUnswitch
    i3 2, label %bb.case2
    i3 3, label %bb.case3
  ]

bb.caseDef:                                       ; preds = %bb.header
  unreachable

bb.case0:                                         ; preds = %bb.header
  br i1 %br.en.5, label %bb.case3, label %bb.latch

bb.case2:                                         ; preds = %bb.header
  br label %bb.toUnswitch

bb.toUnswitch:                                    ; preds = %bb.header, %bb.case2
  %0 = phi i1 [ true, %bb.header ], [ false, %bb.case2 ]
  %1 = phi i8 [ 0, %bb.header ], [ %d.0, %bb.case2 ]
  store volatile i8 %1, ptr addrspace(2) %o, align 4
  br i1 %0, label %bb.latch, label %bb.case3

bb.case3:                                         ; preds = %bb.case0, %bb.toUnswitch, %bb.header
  %d.2 = phi i8 [ %d.0, %bb.header ], [ %d.1, %bb.toUnswitch ], [ %d.1, %bb.case0 ]
  %br.en.1 = phi i1 [ %br.en.2, %bb.header ], [ %0, %bb.toUnswitch ], [ false, %bb.case0 ]
  %d.8 = select i1 %br.en.1, i8 %d.5, i8 %d.6
  store volatile i8 %d.8, ptr addrspace(2) %o, align 4
  br label %bb.latch

bb.latch:                                         ; preds = %bb.case3, %bb.toUnswitch, %bb.case0
  %d.3 = phi i8 [ %d.0, %bb.toUnswitch ], [ %d.1, %bb.case0 ], [ %d.2, %bb.case3 ]
  %br.en.4 = phi i1 [ %0, %bb.toUnswitch ], [ %br.en.3, %bb.case0 ], [ %br.en.1, %bb.case3 ]
  store volatile i8 %d.3, ptr addrspace(2) %o, align 4
  store volatile i1 %br.en.4, ptr addrspace(2) %o, align 4
  br label %bb.header
}
