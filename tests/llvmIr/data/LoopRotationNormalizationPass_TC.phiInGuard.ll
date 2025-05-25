define void @phiInGuard(ptr addrspace(1) %c, ptr addrspace(2) %o) {
entry:
  br label %guard

guard:                                            ; preds = %loopHeader, %guardExit, %entry
  %vInGuard = phi i2 [ -1, %entry ], [ 0, %guardExit ], [ %vInGuard, %loopHeader ]
  %c0 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c0, label %loopHeader.preheader, label %guardExit

loopHeader.preheader:                             ; preds = %guard
  br label %loopHeader

loopHeader:                                       ; preds = %loopHeader.preheader
  br label %guard

guardExit:                                        ; preds = %guard
  store volatile i2 %vInGuard, ptr addrspace(2) %o, align 1
  br label %guard
}
