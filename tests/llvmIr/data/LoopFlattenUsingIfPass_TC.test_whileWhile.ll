define void @test_whileWhile(ptr addrspace(1) %c, ptr addrspace(2) %o) !prof !0 {
entry:
  br label %bb.wh

bb.wh:                                            ; preds = %bb.fn1, %entry
  %isChildLoop.bb.wh.wh = phi i1 [ false, %entry ], [ %isChildLoopInLatch.bb.wh.wh, %bb.fn1 ]
  %v0 = phi i8 [ 0, %entry ], [ %v22, %bb.fn1 ]
  br i1 %isChildLoop.bb.wh.wh, label %bb.wh.split, label %bb.wh.wh

bb.wh.split:                                      ; preds = %bb.wh
  %c0 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c0, label %bb.wh.body, label %bb.wh.exit

bb.wh.body:                                       ; preds = %bb.wh.split
  br label %bb.fn0

bb.fn0:                                           ; preds = %bb.wh.body
  %v1 = add i8 %v0, 1
  br label %bb.wh.wh

bb.wh.wh:                                         ; preds = %bb.wh, %bb.fn0
  %v2 = phi i8 [ %v1, %bb.fn0 ], [ %v0, %bb.wh ]
  %c1 = load volatile i1, ptr addrspace(1) %c, align 1
  br i1 %c1, label %bb.wh.wh.body, label %bb.fn1.oldLatch

bb.wh.wh.body:                                    ; preds = %bb.wh.wh
  %v3 = add i8 %v2, 16
  br label %bb.fn1

bb.fn1.oldLatch:                                  ; preds = %bb.wh.wh
  %v2.lcssa = phi i8 [ %v2, %bb.wh.wh ]
  store volatile i8 %v2.lcssa, ptr addrspace(2) %o, align 1
  br label %bb.fn1

bb.fn1:                                           ; preds = %bb.wh.wh.body, %bb.fn1.oldLatch
  %v22 = phi i8 [ %v3, %bb.wh.wh.body ], [ undef, %bb.fn1.oldLatch ]
  %isChildLoopInLatch.bb.wh.wh = phi i1 [ true, %bb.wh.wh.body ], [ false, %bb.fn1.oldLatch ]
  br label %bb.wh

bb.wh.exit:                                       ; preds = %bb.wh.split
  ret void
}
