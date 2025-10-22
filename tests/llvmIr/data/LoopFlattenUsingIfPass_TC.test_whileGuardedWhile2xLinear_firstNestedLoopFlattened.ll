define void @test_whileGuardedWhile2xLinear_firstNestedLoopFlattened(ptr addrspace(1) %c, ptr addrspace(2) %o, ptr addrspace(3) %i) {
entry:
  br label %bb.wh

bb.wh:                                            ; preds = %bb.fn1, %entry
  %beginTmp2.22.0 = phi i8 [ undef, %entry ], [ %beginTmp2.22.4, %bb.fn1 ]
  %isChildLoop.bb.wh1.wh = phi i1 [ false, %entry ], [ %isChildLoopInLatch.bb.wh1.wh, %bb.fn1 ]
  %beginTmp2.0 = phi i8 [ undef, %entry ], [ %beginTmp2.37, %bb.fn1 ]
  %isChildLoop.bb.wh.wh = phi i1 [ false, %entry ], [ %isChildLoopInLatch.bb.wh.wh8, %bb.fn1 ]
  %v0 = phi i8 [ 0, %entry ], [ %v2.1.inLatch, %bb.fn1 ]
  br i1 %isChildLoop.bb.wh1.wh, label %bb.wh1.wh, label %bb.wh.split1

bb.wh.split1:                                     ; preds = %bb.wh
  br i1 %isChildLoop.bb.wh.wh, label %bb.wh.wh, label %bb.wh.split

bb.wh.split:                                      ; preds = %bb.wh.split1
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
  br i1 %cIf, label %bb.wh.wh.preheader, label %bb.wh1.if

bb.wh.wh.preheader:                               ; preds = %bb.wh.if
  br label %bb.wh.wh

bb.wh.wh:                                         ; preds = %bb.wh.wh.preheader, %bb.wh.split1
  %beginTmp2.1 = phi i8 [ %beginTmp2.0, %bb.wh.split1 ], [ %beginTmp, %bb.wh.wh.preheader ]
  %v2 = phi i8 [ %v1, %bb.wh.wh.preheader ], [ %v0, %bb.wh.split1 ]
  %c1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c1, label %bb.wh.wh.body, label %bb.wh1.if.loopexit

bb.wh.wh.body:                                    ; preds = %bb.wh.wh
  %v3 = add i8 %v2, 16
  br label %bb.fn1.oldLatch6

bb.wh1.if.loopexit:                               ; preds = %bb.wh.wh
  %v2.lcssa = phi i8 [ %v2, %bb.wh.wh ]
  br label %bb.wh1.if

bb.wh1.if:                                        ; preds = %bb.wh1.if.loopexit, %bb.wh.if
  %beginTmp2.2 = phi i8 [ %beginTmp2.1, %bb.wh1.if.loopexit ], [ %beginTmp, %bb.wh.if ]
  %v1.1 = phi i8 [ %v1, %bb.wh.if ], [ %v2.lcssa, %bb.wh1.if.loopexit ]
  %cIf.1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %cIf.1, label %bb.wh1.wh.preheader, label %bb.fn1.oldLatch

bb.wh1.wh.preheader:                              ; preds = %bb.wh1.if
  br label %bb.wh1.wh

bb.wh1.wh:                                        ; preds = %bb.wh, %bb.wh1.wh.preheader
  %beginTmp2.22.1 = phi i8 [ %beginTmp2.22.0, %bb.wh ], [ %beginTmp2.2, %bb.wh1.wh.preheader ]
  %v2.1 = phi i8 [ %v0, %bb.wh ], [ %v1.1, %bb.wh1.wh.preheader ]
  %c1.1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c1.1, label %bb.wh1.wh.body, label %bb.fn1.loopexit

bb.wh1.wh.body:                                   ; preds = %bb.wh1.wh
  %v3.1 = add i8 %v2.1, 16
  br label %bb.fn1

bb.fn1.loopexit:                                  ; preds = %bb.wh1.wh
  %v2.1.lcssa = phi i8 [ %v2.1, %bb.wh1.wh ]
  br label %bb.fn1.oldLatch

bb.fn1.oldLatch:                                  ; preds = %bb.fn1.loopexit, %bb.wh1.if
  %beginTmp2.22.2 = phi i8 [ %beginTmp2.22.1, %bb.fn1.loopexit ], [ %beginTmp2.2, %bb.wh1.if ]
  %v4 = phi i8 [ %v1.1, %bb.wh1.if ], [ %v2.1.lcssa, %bb.fn1.loopexit ]
  store volatile i8 %v4, ptr addrspace(2) %o, align 1
  store volatile i8 %beginTmp2.22.2, ptr addrspace(2) %o, align 1
  br label %bb.fn1.oldLatch6

bb.fn1.oldLatch6:                                 ; preds = %bb.wh.wh.body, %bb.fn1.oldLatch
  %beginTmp2.22.3 = phi i8 [ %beginTmp2.22.2, %bb.fn1.oldLatch ], [ %beginTmp2.22.0, %bb.wh.wh.body ]
  %beginTmp2.3 = phi i8 [ %beginTmp2.1, %bb.wh.wh.body ], [ %beginTmp2.22.2, %bb.fn1.oldLatch ]
  %v2.inLatch = phi i8 [ %v3, %bb.wh.wh.body ], [ %v4, %bb.fn1.oldLatch ]
  %isChildLoopInLatch.bb.wh.wh = phi i1 [ true, %bb.wh.wh.body ], [ false, %bb.fn1.oldLatch ]
  br label %bb.fn1

bb.fn1:                                           ; preds = %bb.wh1.wh.body, %bb.fn1.oldLatch6
  %beginTmp2.22.4 = phi i8 [ %beginTmp2.22.1, %bb.wh1.wh.body ], [ %beginTmp2.22.3, %bb.fn1.oldLatch6 ]
  %v2.1.inLatch = phi i8 [ %v3.1, %bb.wh1.wh.body ], [ %v2.inLatch, %bb.fn1.oldLatch6 ]
  %beginTmp2.37 = phi i8 [ poison, %bb.wh1.wh.body ], [ %beginTmp2.3, %bb.fn1.oldLatch6 ]
  %isChildLoopInLatch.bb.wh.wh8 = phi i1 [ poison, %bb.wh1.wh.body ], [ %isChildLoopInLatch.bb.wh.wh, %bb.fn1.oldLatch6 ]
  %isChildLoopInLatch.bb.wh1.wh = phi i1 [ true, %bb.wh1.wh.body ], [ false, %bb.fn1.oldLatch6 ]
  br label %bb.wh

bb.wh.exit:                                       ; preds = %bb.wh.split
  ret void
}
