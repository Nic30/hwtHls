define void @test_uselessSuffix(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
entry:
  br label %bb0

bb0:                                              ; preds = %bb.case16, %bb.case8, %bb.case0, %bb.default, %entry
  %v = load volatile i2, ptr addrspace(1) %dataIn, align 4
  switch i2 %v, label %bb.default [
    i2 0, label %bb.case0
    i2 1, label %bb.case8
    i2 -2, label %bb.case16
  ]

bb.default:                                       ; preds = %bb0
  store volatile i8 15, ptr addrspace(2) %dataOut, align 4
  br label %bb0

bb.case0:                                         ; preds = %bb0
  store volatile i8 0, ptr addrspace(2) %dataOut, align 4
  br label %bb0

bb.case8:                                         ; preds = %bb0
  store volatile i8 8, ptr addrspace(2) %dataOut, align 4
  br label %bb0

bb.case16:                                        ; preds = %bb0
  store volatile i8 16, ptr addrspace(2) %dataOut, align 4
  br label %bb0
}
