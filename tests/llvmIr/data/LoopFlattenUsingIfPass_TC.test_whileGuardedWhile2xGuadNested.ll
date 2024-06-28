define void @test_whileGuardedWhile2xGuadNested(ptr addrspace(1) %c, ptr addrspace(2) %o, ptr addrspace(3) %i) !prof !0 {
entry:
  br label %bb.wh

bb.wh:                                            ; preds = %bb.fn1, %entry
  %beginTmp2.16.0 = phi i8 [ undef, %entry ], [ %beginTmp2.16.3, %bb.fn1 ]
  %isChildLoop.bb.wh1.wh = phi i1 [ false, %entry ], [ %isChildLoopInLatch.bb.wh1.wh, %bb.fn1 ]
  %beginTmp2.0 = phi i8 [ undef, %entry ], [ %beginTmp2.3, %bb.fn1 ]
  %isChildLoop.bb.wh.wh = phi i1 [ false, %entry ], [ %isChildLoopInLatch.bb.wh.wh, %bb.fn1 ]
  %v0 = phi i8 [ 0, %entry ], [ %v2.110, %bb.fn1 ]
  br i1 %isChildLoop.bb.wh1.wh, label %bb.wh.split4, label %bb.wh1.wh

bb.wh.split4:                                     ; preds = %bb.wh
  br i1 %isChildLoop.bb.wh.wh, label %bb.wh.split, label %bb.wh.wh

bb.wh.split:                                      ; preds = %bb.wh.split4
  %c0 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c0, label %bb.wh.body, label %bb.wh.exit

bb.wh.body:                                       ; preds = %bb.wh.split
  br label %bb.fn0

bb.fn0:                                           ; preds = %bb.wh.body
  %v1 = add i8 %v0, 1
  %beginTmp = load volatile i8, ptr addrspace(3) %i, align 1
  br label %bb.wh.if

bb.wh.if:                                         ; preds = %bb.fn0
  %cIf = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %cIf, label %bb.wh.wh.preheader, label %bb.fn1.oldLatch

bb.wh.wh.preheader:                               ; preds = %bb.wh.if
  br label %bb.wh.wh

bb.wh.wh:                                         ; preds = %bb.wh.split4, %bb.wh.wh.preheader
  %beginTmp2.1 = phi i8 [ %beginTmp, %bb.wh.wh.preheader ], [ %beginTmp2.0, %bb.wh.split4 ]
  %v2 = phi i8 [ %v1, %bb.wh.wh.preheader ], [ %v0, %bb.wh.split4 ]
  %c1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c1, label %bb.wh.wh.body, label %bb.wh1.if

bb.wh.wh.body:                                    ; preds = %bb.wh.wh
  %v3 = add i8 %v2, 16
  br label %bb.fn1

bb.wh1.if:                                        ; preds = %bb.wh.wh
  %v1.1 = phi i8 [ %v2, %bb.wh.wh ]
  %cIf.1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %cIf.1, label %bb.wh1.wh.preheader, label %bb.fn1.oldLatch

bb.wh1.wh.preheader:                              ; preds = %bb.wh1.if
  br label %bb.wh1.wh

bb.wh1.wh:                                        ; preds = %bb.wh, %bb.wh1.wh.preheader
  %beginTmp2.16.1 = phi i8 [ %beginTmp2.1, %bb.wh1.wh.preheader ], [ %beginTmp2.16.0, %bb.wh ]
  %v2.1 = phi i8 [ %v1.1, %bb.wh1.wh.preheader ], [ %v0, %bb.wh ]
  %c1.1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c1.1, label %bb.wh1.wh.body, label %bb.fn1.loopexit

bb.wh1.wh.body:                                   ; preds = %bb.wh1.wh
  %v3.1 = add i8 %v2.1, 16
  br label %bb.fn1

bb.fn1.loopexit:                                  ; preds = %bb.wh1.wh
  %v2.1.lcssa = phi i8 [ %v2.1, %bb.wh1.wh ]
  br label %bb.fn1.oldLatch

bb.fn1.oldLatch:                                  ; preds = %bb.wh.if, %bb.wh1.if, %bb.fn1.loopexit
  %beginTmp2.16.2 = phi i8 [ %beginTmp2.16.1, %bb.fn1.loopexit ], [ %beginTmp2.1, %bb.wh1.if ], [ %beginTmp2.16.0, %bb.wh.if ]
  %beginTmp2.2 = phi i8 [ %beginTmp2.16.1, %bb.fn1.loopexit ], [ %beginTmp2.1, %bb.wh1.if ], [ %beginTmp, %bb.wh.if ]
  %v4 = phi i8 [ %v1, %bb.wh.if ], [ %v1.1, %bb.wh1.if ], [ %v2.1.lcssa, %bb.fn1.loopexit ]
  store volatile i8 %v4, ptr addrspace(2) %o, align 1
  store volatile i8 %beginTmp2.2, ptr addrspace(2) %o, align 1
  br label %bb.fn1

bb.fn1:                                           ; preds = %bb.wh1.wh.body, %bb.wh.wh.body, %bb.fn1.oldLatch
  %beginTmp2.16.3 = phi i8 [ %beginTmp2.1, %bb.wh.wh.body ], [ %beginTmp2.16.1, %bb.wh1.wh.body ], [ %beginTmp2.16.2, %bb.fn1.oldLatch ]
  %beginTmp2.3 = phi i8 [ %beginTmp2.1, %bb.wh.wh.body ], [ %beginTmp2.2, %bb.fn1.oldLatch ], [ undef, %bb.wh1.wh.body ]
  %v23 = phi i8 [ %v3, %bb.wh.wh.body ], [ undef, %bb.fn1.oldLatch ], [ undef, %bb.wh1.wh.body ]
  %isChildLoopInLatch.bb.wh.wh = phi i1 [ true, %bb.wh.wh.body ], [ false, %bb.fn1.oldLatch ], [ undef, %bb.wh1.wh.body ]
  %v2.110 = phi i8 [ %v3.1, %bb.wh1.wh.body ], [ undef, %bb.wh.wh.body ], [ undef, %bb.fn1.oldLatch ]
  %isChildLoopInLatch.bb.wh1.wh = phi i1 [ true, %bb.wh1.wh.body ], [ true, %bb.wh.wh.body ], [ true, %bb.fn1.oldLatch ]
  br label %bb.wh

bb.wh.exit:                                       ; preds = %bb.wh.split
  ret void
}
