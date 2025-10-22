define void @test_whileWhile2xNested(ptr addrspace(1) %c, ptr addrspace(2) %o) {
entry:
  br label %bb.wh

bb.wh:                                            ; preds = %bb.fn1, %entry
  %isChildLoop.bb.wh1 = phi i1 [ false, %entry ], [ %isChildLoopInLatch.bb.wh1, %bb.fn1 ]
  %v0 = phi i8 [ 0, %entry ], [ %v2.inLatch, %bb.fn1 ]
  %isChildLoop.bb.wh2.inChildHeader = phi i1 [ poison, %entry ], [ %isChildLoop.bb.wh2.inLatch, %bb.fn1 ]
  %v2.2.inChildHeader.inChildHeader = phi i8 [ poison, %entry ], [ %v2.2.inChildHeader.inLatch, %bb.fn1 ]
  br i1 %isChildLoop.bb.wh1, label %bb.wh1, label %bb.wh.split

bb.wh.split:                                      ; preds = %bb.wh
  %c0 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c0, label %bb.wh.body, label %bb.wh.exit

bb.wh.body:                                       ; preds = %bb.wh.split
  br label %bb.fn0

bb.fn0:                                           ; preds = %bb.wh.body
  %v1 = add i8 %v0, 1
  br label %bb.wh1

bb.wh1:                                           ; preds = %bb.wh, %bb.fn0
  %isChildLoop.bb.wh2 = phi i1 [ %isChildLoop.bb.wh2.inChildHeader, %bb.wh ], [ false, %bb.fn0 ]
  %v2 = phi i8 [ %v0, %bb.wh ], [ %v1, %bb.fn0 ]
  %v2.2.inChildHeader = phi i8 [ %v2.2.inChildHeader.inChildHeader, %bb.wh ], [ poison, %bb.fn0 ]
  br i1 %isChildLoop.bb.wh2, label %bb.wh2, label %bb.wh1.split

bb.wh1.split:                                     ; preds = %bb.wh1
  %c1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c1, label %bb.wh1.body, label %bb.fn1.oldLatch

bb.wh1.body:                                      ; preds = %bb.wh1.split
  %v3 = add i8 %v2, 16
  br label %bb.wh2

bb.wh2:                                           ; preds = %bb.wh1, %bb.wh1.body
  %v2.2 = phi i8 [ %v2.2.inChildHeader, %bb.wh1 ], [ %v3, %bb.wh1.body ]
  %c1.2 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c1.2, label %bb.wh2.body, label %bb.wh1.body.end.oldLatch

bb.wh2.body:                                      ; preds = %bb.wh2
  %v3.2 = add i8 %v2, 16
  br label %bb.wh1.body.end

bb.wh1.body.end.oldLatch:                         ; preds = %bb.wh2
  %v2.2.lcssa = phi i8 [ %v2.2, %bb.wh2 ]
  store volatile i8 %v2.2.lcssa, ptr addrspace(2) %o, align 1
  br label %bb.wh1.body.end

bb.wh1.body.end:                                  ; preds = %bb.wh2.body, %bb.wh1.body.end.oldLatch
  %v2.2.inLatch = phi i8 [ %v3.2, %bb.wh2.body ], [ poison, %bb.wh1.body.end.oldLatch ]
  %v2.2.lcssa2 = phi i8 [ poison, %bb.wh2.body ], [ %v2.2.lcssa, %bb.wh1.body.end.oldLatch ]
  %isChildLoopInLatch.bb.wh2 = phi i1 [ true, %bb.wh2.body ], [ false, %bb.wh1.body.end.oldLatch ]
  br label %bb.fn1

bb.fn1.oldLatch:                                  ; preds = %bb.wh1.split
  %v2.lcssa = phi i8 [ %v2, %bb.wh1.split ]
  store volatile i8 %v2.lcssa, ptr addrspace(2) %o, align 1
  br label %bb.fn1

bb.fn1:                                           ; preds = %bb.wh1.body.end, %bb.fn1.oldLatch
  %isChildLoop.bb.wh2.inLatch = phi i1 [ %isChildLoopInLatch.bb.wh2, %bb.wh1.body.end ], [ poison, %bb.fn1.oldLatch ]
  %v2.inLatch = phi i8 [ %v2.2.lcssa2, %bb.wh1.body.end ], [ %v2.lcssa, %bb.fn1.oldLatch ]
  %v2.2.inChildHeader.inLatch = phi i8 [ %v2.2.inLatch, %bb.wh1.body.end ], [ poison, %bb.fn1.oldLatch ]
  %isChildLoopInLatch.bb.wh1 = phi i1 [ true, %bb.wh1.body.end ], [ false, %bb.fn1.oldLatch ]
  br label %bb.wh

bb.wh.exit:                                       ; preds = %bb.wh.split
  ret void
}
