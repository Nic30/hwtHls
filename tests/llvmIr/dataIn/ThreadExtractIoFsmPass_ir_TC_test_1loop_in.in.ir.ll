; ModuleID = 'hwtHlsModule'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @ThreadExtractIoFsmPass_ir_TC.test_1loop_in(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.loop.head

bb.loop.head:
  %r0 = load volatile i37, ptr addrspace(1) %rx, align 8
  store volatile i37 %r0, ptr addrspace(2) %tx, align 8
  br label %bb.loop.head
}

!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2, !3}
!2 = !{!"IN", i64 0, i64 37, i64 0, ptr null, i64 0, !4}
!3 = !{!"OUT", i64 0, i64 37, i64 37, ptr null, i64 1}
!4 = !{!"hwthls.thread.extractiofsm", i32 1, i32 0}
