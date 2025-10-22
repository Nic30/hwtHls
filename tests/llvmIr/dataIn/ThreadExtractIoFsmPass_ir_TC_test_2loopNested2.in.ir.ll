; ModuleID = 'hwtHlsModule'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @ThreadExtractIoFsmPass_ir_TC.test_2loopNested2(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.L0.head

bb.L0.head:
  %r0 = load volatile i37, ptr addrspace(1) %rx, align 8
  br label %bb.L1.head

bb.L1.head:
  %r1 = load volatile i37, ptr addrspace(1) %rx, align 8
  %r2 = load volatile i37, ptr addrspace(1) %rx, align 8
  store volatile i37 %r1, ptr addrspace(2) %tx, align 8
  %L1ExitCond = icmp eq i37 %r1, 0
  br i1 %L1ExitCond, label %bb.L0.latch, label %bb.L1.head

bb.L0.latch:
  store volatile i37 %r0, ptr addrspace(2) %tx, align 8
  store volatile i37 %r2, ptr addrspace(2) %tx, align 8
  br label %bb.L0.head
}

!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2, !5}
!2 = !{!"IN", i64 0, i64 37, i64 0, ptr null, i64 0, !3}
!3 = !{!"hwtHls.io.protocol", !4}
!4 = !{!"hwtHls.io.protocol.stream", i32 32, i32 8, !"mask", i32 0, !"eof", i32 0, i32 1}
!5 = !{!"OUT", i64 0, i64 37, i64 37, ptr null, i64 1, !3, !6}
!6 = !{!"hwthls.thread.extractiofsm", i32 1, i32 0}
