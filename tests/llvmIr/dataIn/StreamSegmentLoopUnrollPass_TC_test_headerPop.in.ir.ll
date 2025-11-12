; ModuleID = 'hwtHlsModule'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @StreamSegmentLoopUnrollPass_TC.headerPop(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb1

bb1:
  %r0 = load volatile i134, ptr addrspace(1) %rx, align 32
  %r0.eof = icmp ne i134 %r0, 0
  br i1 %r0.eof, label %bb1.backedge, label %bb1.segmentEnCheck.after

bb1.segmentEnCheck.after:
  %r1 = load volatile i134, ptr addrspace(1) %rx, align 32
  br label %bb.forwardUntilEoF

bb.forwardUntilEoF:
  %r.phi = phi i134 [ %r1, %bb1.segmentEnCheck.after ], [ %r2, %bb.forwardUntilEoF ]
  %r2 = load volatile i134, ptr addrspace(1) %rx, align 32
  %r2.eof = icmp ne i134 %r2, 0
  %r2.ext = zext i134 %r2 to i135
  store volatile i135 %r2.ext, ptr addrspace(2) %tx, align 32
  br i1 %r2.eof, label %bb.consumePendingOnLast, label %bb.forwardUntilEoF

bb.consumePendingOnLast:
  %r.phi.ext = zext i134 %r.phi to i135
  store volatile i135 %r.phi.ext, ptr addrspace(2) %tx, align 32
  br label %bb1.backedge

bb1.backedge:
  br label %bb1, !llvm.loop !6
}


!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2, !4}
!2 = !{!"IN", i64 0, i64 268, i64 0, ptr null, i64 0, !3}
!3 = !{!"hwtHls.io.protocol", !4}
!4 = !{!"hwtHls.io.protocol.stream", i32 128, i32 8, !"enable+empty", i32 0, !"eof", i32 0, i32 2}
!5 = !{!"OUT", i64 0, i64 268, i64 268, ptr null, i64 1, !3}
!6 = distinct !{!6, !7}
!7 = !{!"hwthls.loop.streamsegmentunroll.io", i32 0}
