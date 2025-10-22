; ModuleID = 'test'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @inDepsSyncBeginEnd(ptr addrspace(1) %i0, ptr addrspace(2) %o0, ptr addrspace(3) %agrInArg, ptr addrspace(4) %threadEndSync.inDepsSyncBeginEnd.t1.loc) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.mainLoop.threadSplit.begint1

bb.mainLoop.threadSplit.begint1:                  ; preds = %bb0, %bb.mainLoop.threadSplit.end.t1
  store volatile i8 0, ptr addrspace(2) %o0, align 1
  %i.v0 = load volatile i8, ptr addrspace(1) %i0, align 1
  %i.v1 = load volatile i8, ptr addrspace(1) %i0, align 1
  br label %threadSplitCodeRepl

threadSplitCodeRepl:                              ; preds = %bb.mainLoop.threadSplit.begint1
  %0 = call i16 @hwtHls.bitConcat.i8.i8(i8 %i.v0, i8 %i.v1) #2
  store volatile i16 %0, ptr addrspace(3) %agrInArg, align 2
  %threadEndSync.inDepsSyncBeginEnd.t1.reload = load volatile i1, ptr addrspace(4) %threadEndSync.inDepsSyncBeginEnd.t1.loc, align 1
  br label %bb.mainLoop.threadSplit.end.t1

bb.mainLoop.threadSplit.end.t1:                   ; preds = %threadSplitCodeRepl
  br label %bb.mainLoop.threadSplit.begint1
}

; Function Attrs: noreturn
define internal void @inDepsSyncBeginEnd.t1(ptr addrspace(1) %o1, ptr addrspace(2) %0, ptr addrspace(3) %threadEndSync.inDepsSyncBeginEnd.t1.o) #0 !hwtHls.io !6 {
threadEntry:
  br label %newFuncRoot

newFuncRoot:                                      ; preds = %bb.mainLoop.threadSplit.end.t1.exitStub, %threadEntry
  %i.v0 = load volatile i16, ptr addrspace(2) %0, align 2
  %1 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %i.v0, i5 0) #2
  %2 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %i.v0, i5 8) #2
  br label %bb.mainLoop

bb.mainLoop:                                      ; preds = %newFuncRoot
  store volatile i8 %1, ptr addrspace(1) %o1, align 1
  store volatile i8 %2, ptr addrspace(1) %o1, align 1
  %threadEndSync.inDepsSyncBeginEnd.t1 = freeze i1 true
  store volatile i1 %threadEndSync.inDepsSyncBeginEnd.t1, ptr addrspace(3) %threadEndSync.inDepsSyncBeginEnd.t1.o, align 1
  br label %bb.mainLoop.threadSplit.end.t1.exitStub

bb.mainLoop.threadSplit.end.t1.exitStub:          ; preds = %bb.mainLoop
  br label %newFuncRoot
}

; Function Attrs: nofree nounwind speculatable willreturn
declare i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16, i5) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16, i5) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i16 @hwtHls.bitConcat.i8.i8(i8, i8) #1

attributes #0 = { noreturn }
attributes #1 = { nofree nounwind speculatable willreturn }
attributes #2 = { memory(none) }

!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2, !3, !4, !5}
!2 = !{!"IN", i64 0, i64 8, i64 8, ptr null, i64 0}
!3 = !{!"OUT", i64 0, i64 8, i64 8, ptr null, i64 1}
!4 = !{!"OUT", i64 0, i64 0, i64 16, ptr @inDepsSyncBeginEnd.t1, i64 1}
!5 = !{!"IN", i64 0, i64 1, i64 0, ptr @inDepsSyncBeginEnd.t1, i64 2}
!6 = distinct !{!7, !8, !9}
!7 = !{!"OUT", i64 0, i64 8, i64 8, ptr null, i64 2}
!8 = !{!"IN", i64 0, i64 16, i64 0, ptr @inDepsSyncBeginEnd, i64 2}
!9 = !{!"OUT", i64 0, i64 0, i64 1, ptr @inDepsSyncBeginEnd, i64 3}
