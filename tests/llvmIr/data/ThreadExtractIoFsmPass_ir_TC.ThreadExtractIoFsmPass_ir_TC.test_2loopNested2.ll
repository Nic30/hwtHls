; ModuleID = 'test'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @ThreadExtractIoFsmPass_ir_TC.test_2loopNested2(ptr addrspace(1) %rx, ptr addrspace(2) %0, ptr addrspace(3) %1) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.L0.head

bb.L0.head:                                       ; preds = %bb.L0.latch, %bb0
  %r0 = load volatile i37, ptr addrspace(1) %rx, align 8
  store volatile i37 %r0, ptr addrspace(2) %0, align 8
  br label %bb.L1.head

bb.L1.head:                                       ; preds = %bb.L1.head.newLatch, %bb.L0.head
  %r1 = load volatile i37, ptr addrspace(1) %rx, align 8
  %r2 = load volatile i37, ptr addrspace(1) %rx, align 8
  %L1ExitCond = icmp eq i37 %r1, 0
  br label %bb.L1.head.newLatch

bb.L1.head.newLatch:                              ; preds = %bb.L1.head
  %2 = call i75 @hwtHls.bitConcat.i37.i37.i1(i37 %r1, i37 %r2, i1 %L1ExitCond) #1
  store volatile i75 %2, ptr addrspace(3) %1, align 16
  br i1 %L1ExitCond, label %bb.L0.latch, label %bb.L1.head

bb.L0.latch:                                      ; preds = %bb.L1.head.newLatch
  br label %bb.L0.head
}

define void @ThreadExtractIoFsmPass_ir_TC.test_2loopNested2.ioFsmExtract.tx(ptr addrspace(1) %tx, ptr addrspace(2) %0, ptr addrspace(3) %1) !prof !0 !hwtHls.io !8 {
bb0:
  br label %bb.L0.head

bb.L0.head:                                       ; preds = %bb.L0.latch, %bb0
  %r0 = load i37, ptr addrspace(2) %0, align 8
  br label %bb.L1.head

bb.L1.head:                                       ; preds = %bb.L1.head.newLatch, %bb.L0.head
  %2 = load i75, ptr addrspace(3) %1, align 16
  %r1 = call i37 @hwtHls.bitRangeGet.i75.i8.i37.0(i75 %2, i8 0) #1
  %r2 = call i37 @hwtHls.bitRangeGet.i75.i8.i37.37(i75 %2, i8 37) #1
  %L1ExitCond = call i1 @hwtHls.bitRangeGet.i75.i8.i1.74(i75 %2, i8 74) #1
  store volatile i37 %r1, ptr addrspace(1) %tx, align 8
  br label %bb.L1.head.newLatch

bb.L1.head.newLatch:                              ; preds = %bb.L1.head
  br i1 %L1ExitCond, label %bb.L0.latch, label %bb.L1.head

bb.L0.latch:                                      ; preds = %bb.L1.head.newLatch
  store volatile i37 %r0, ptr addrspace(1) %tx, align 8
  store volatile i37 %r2, ptr addrspace(1) %tx, align 8
  br label %bb.L0.head
}

; Function Attrs: nofree nounwind speculatable willreturn
declare i75 @hwtHls.bitConcat.i37.i37.i1(i37, i37, i1) #0

; Function Attrs: nofree nounwind speculatable willreturn
declare i37 @hwtHls.bitRangeGet.i75.i8.i37.0(i75, i8) #0

; Function Attrs: nofree nounwind speculatable willreturn
declare i37 @hwtHls.bitRangeGet.i75.i8.i37.37(i75, i8) #0

; Function Attrs: nofree nounwind speculatable willreturn
declare i1 @hwtHls.bitRangeGet.i75.i8.i1.74(i75, i8) #0

attributes #0 = { nofree nounwind speculatable willreturn }
attributes #1 = { memory(none) }

!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2, !5, !7}
!2 = !{!"IN", i64 0, i64 37, i64 0, ptr null, i64 0, !3}
!3 = !{!"hwtHls.io.protocol", !4}
!4 = !{!"hwtHls.io.protocol.stream", i32 32, i32 8, !"mask", i32 0, !"eof", i32 0, i32 1}
!5 = !{!"OUT", i64 0, i64 1, i64 37, ptr @ThreadExtractIoFsmPass_ir_TC.test_2loopNested2.ioFsmExtract.tx, i64 1, !6}
!6 = !{!"hwtHls.io.buffercapacity", i64 1}
!7 = !{!"OUT", i64 0, i64 1, i64 75, ptr @ThreadExtractIoFsmPass_ir_TC.test_2loopNested2.ioFsmExtract.tx, i64 2, !6}
!8 = distinct !{!9, !10, !11}
!9 = !{!"OUT", i64 0, i64 37, i64 37, ptr null, i64 1, !3}
!10 = !{!"IN", i64 0, i64 1, i64 37, ptr @ThreadExtractIoFsmPass_ir_TC.test_2loopNested2, i64 1}
!11 = !{!"IN", i64 0, i64 1, i64 75, ptr @ThreadExtractIoFsmPass_ir_TC.test_2loopNested2, i64 2}
