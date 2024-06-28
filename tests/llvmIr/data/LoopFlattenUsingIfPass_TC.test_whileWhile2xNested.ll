define void @test_whileWhile2xNested(ptr addrspace(1) %c, ptr addrspace(2) %o) !prof !0 {
entry:
  br label %bb.wh

bb.wh:                                            ; preds = %bb.fn1, %entry
  %isChildLoop.bb.wh1 = phi i1 [ false, %entry ], [ %isChildLoopInLatch.bb.wh1, %bb.fn1 ]
  %v0 = phi i8 [ 0, %entry ], [ %v28, %bb.fn1 ]
  %isChildLoop.bb.wh26 = phi i1 [ undef, %entry ], [ %isChildLoop.bb.wh27, %bb.fn1 ]
  %v2.229 = phi i8 [ undef, %entry ], [ %v2.2210, %bb.fn1 ]
  br i1 %isChildLoop.bb.wh1, label %bb.wh.split, label %bb.wh1

bb.wh.split:                                      ; preds = %bb.wh
  %c0 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c0, label %bb.wh.body, label %bb.wh.exit

bb.wh.body:                                       ; preds = %bb.wh.split
  br label %bb.fn0

bb.fn0:                                           ; preds = %bb.wh.body
  %v1 = add i8 %v0, 1
  br label %bb.wh1

bb.wh1:                                           ; preds = %bb.wh, %bb.fn0
  %isChildLoop.bb.wh2 = phi i1 [ false, %bb.fn0 ], [ %isChildLoop.bb.wh26, %bb.wh ]
  %v2 = phi i8 [ %v1, %bb.fn0 ], [ %v0, %bb.wh ]
  %v2.22 = phi i8 [ undef, %bb.fn0 ], [ %v2.229, %bb.wh ]
  br i1 %isChildLoop.bb.wh2, label %bb.wh1.split, label %bb.wh2

bb.wh1.split:                                     ; preds = %bb.wh1
  %c1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c1, label %bb.wh1.body, label %bb.fn1.oldLatch

bb.wh1.body:                                      ; preds = %bb.wh1.split
  %v3 = add i8 %v2, 16
  br label %bb.wh2

bb.wh2:                                           ; preds = %bb.wh1, %bb.wh1.body
  %v2.2 = phi i8 [ %v3, %bb.wh1.body ], [ %v2.22, %bb.wh1 ]
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
  %v2.23 = phi i8 [ %v3.2, %bb.wh2.body ], [ undef, %bb.wh1.body.end.oldLatch ]
  %v2.2.lcssa4 = phi i8 [ %v2.2.lcssa, %bb.wh1.body.end.oldLatch ], [ undef, %bb.wh2.body ]
  %isChildLoopInLatch.bb.wh2 = phi i1 [ true, %bb.wh2.body ], [ false, %bb.wh1.body.end.oldLatch ]
  br label %bb.fn1

bb.fn1.oldLatch:                                  ; preds = %bb.wh1.split
  %v2.lcssa = phi i8 [ %v2, %bb.wh1.split ]
  store volatile i8 %v2.lcssa, ptr addrspace(2) %o, align 1
  br label %bb.fn1

bb.fn1:                                           ; preds = %bb.wh1.body.end, %bb.fn1.oldLatch
  %isChildLoop.bb.wh27 = phi i1 [ %isChildLoopInLatch.bb.wh2, %bb.wh1.body.end ], [ undef, %bb.fn1.oldLatch ]
  %v28 = phi i8 [ %v2.2.lcssa4, %bb.wh1.body.end ], [ undef, %bb.fn1.oldLatch ]
  %v2.2210 = phi i8 [ %v2.23, %bb.wh1.body.end ], [ undef, %bb.fn1.oldLatch ]
  %isChildLoopInLatch.bb.wh1 = phi i1 [ true, %bb.wh1.body.end ], [ false, %bb.fn1.oldLatch ]
  br label %bb.wh

bb.wh.exit:                                       ; preds = %bb.wh.split
  ret void
}
