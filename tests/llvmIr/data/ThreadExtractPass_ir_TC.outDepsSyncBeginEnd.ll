; ModuleID = 'test'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @outDepsSyncBeginEnd(ptr addrspace(1) %dataOut0, ptr addrspace(2) %t1.threadBeginSync1, ptr addrspace(3) %AggregatedOutTmp) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.mainLoop.threadSplit.begint1

bb.mainLoop.threadSplit.begint1:                  ; preds = %bb0, %bb.mainLoop.threadSplit.end.t1
  store volatile i8 0, ptr addrspace(1) %dataOut0, align 1
  br label %codeRepl

codeRepl:                                         ; preds = %bb.mainLoop.threadSplit.begint1
  store volatile i1 true, ptr addrspace(2) %t1.threadBeginSync1, align 1
  %aggregatedOut.ld = load volatile i16, ptr addrspace(3) %AggregatedOutTmp, align 2
  %v0.reload = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %aggregatedOut.ld, i5 0) #2
  %v1.reload = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %aggregatedOut.ld, i5 8) #2
  br label %bb.mainLoop.threadSplit.end.t1

bb.mainLoop.threadSplit.end.t1:                   ; preds = %codeRepl
  store volatile i8 %v0.reload, ptr addrspace(1) %dataOut0, align 1
  store volatile i8 %v1.reload, ptr addrspace(1) %dataOut0, align 1
  br label %bb.mainLoop.threadSplit.begint1
}

; Function Attrs: noreturn
define internal void @outDepsSyncBeginEnd.t1(ptr addrspace(1) %dataOut1, ptr addrspace(2) %t1.threadBeginSync.i, ptr addrspace(3) %0) #0 !hwtHls.io !5 {
threadEntry:
  br label %newFuncRoot

newFuncRoot:                                      ; preds = %bb.mainLoop.threadSplit.end.t1.exitStub, %threadEntry
  %t1.threadBeginSync = load volatile i1, ptr addrspace(2) %t1.threadBeginSync.i, align 1
  br label %bb.mainLoop

bb.mainLoop:                                      ; preds = %newFuncRoot
  store volatile i8 1, ptr addrspace(1) %dataOut1, align 1
  %v0 = freeze i8 99
  %v1 = freeze i8 100
  br label %bb.mainLoop.threadSplit.end.t1.exitStub

bb.mainLoop.threadSplit.end.t1.exitStub:          ; preds = %bb.mainLoop
  %AggregatedOut.val = call i16 @hwtHls.bitConcat.i8.i8(i8 %v0, i8 %v1) #2
  store volatile i16 %AggregatedOut.val, ptr addrspace(3) %0, align 2
  br label %newFuncRoot
}

; Function Attrs: nofree nounwind speculatable willreturn
declare i16 @hwtHls.bitConcat.i8.i8(i8, i8) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16, i5) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16, i5) #1

attributes #0 = { noreturn }
attributes #1 = { nofree nounwind speculatable willreturn }
attributes #2 = { memory(none) }

!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2, !3, !4}
!2 = !{!"OUT", i64 0, i64 0, i64 0, ptr null, i64 0}
!3 = !{!"OUT", i64 0, i64 0, i64 1, ptr @outDepsSyncBeginEnd.t1, i64 1}
!4 = !{!"IN", i64 0, i64 16, i64 0, ptr @outDepsSyncBeginEnd.t1, i64 2}
!5 = distinct !{!6, !7, !8}
!6 = !{!"OUT", i64 0, i64 0, i64 0, ptr null, i64 1}
!7 = !{!"IN", i64 0, i64 1, i64 0, ptr @outDepsSyncBeginEnd, i64 1}
!8 = !{!"OUT", i64 0, i64 0, i64 16, ptr @outDepsSyncBeginEnd, i64 2}
