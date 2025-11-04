; ModuleID = 'test'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @noDepsSyncBeginEnd(ptr addrspace(1) %dataOut0, ptr addrspace(2) %t1.threadBeginSync1, ptr addrspace(3) %t1.threadEndSync.loc) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.mainLoop.threadSplit.begint1

bb.mainLoop.threadSplit.begint1:                  ; preds = %bb0, %bb.mainLoop.threadSplit.end.t1
  store volatile i8 0, ptr addrspace(1) %dataOut0, align 1
  br label %codeRepl

codeRepl:                                         ; preds = %bb.mainLoop.threadSplit.begint1
  store volatile i1 true, ptr addrspace(2) %t1.threadBeginSync1, align 1
  %t1.threadEndSync.reload = load volatile i1, ptr addrspace(3) %t1.threadEndSync.loc, align 1
  br label %bb.mainLoop.threadSplit.end.t1

bb.mainLoop.threadSplit.end.t1:                   ; preds = %codeRepl
  br label %bb.mainLoop.threadSplit.begint1
}

; Function Attrs: noreturn
define internal void @noDepsSyncBeginEnd.t1(ptr addrspace(1) %dataOut1, ptr addrspace(2) %t1.threadBeginSync.i, ptr addrspace(3) %t1.threadEndSync.o) #0 !hwtHls.io !5 {
threadEntry:
  br label %newFuncRoot

newFuncRoot:                                      ; preds = %bb.mainLoop.threadSplit.end.t1.exitStub, %threadEntry
  %t1.threadBeginSync = load volatile i1, ptr addrspace(2) %t1.threadBeginSync.i, align 1
  br label %bb.mainLoop

bb.mainLoop:                                      ; preds = %newFuncRoot
  store volatile i8 1, ptr addrspace(1) %dataOut1, align 1
  store volatile i1 true, ptr addrspace(3) %t1.threadEndSync.o, align 1
  br label %bb.mainLoop.threadSplit.end.t1.exitStub

bb.mainLoop.threadSplit.end.t1.exitStub:          ; preds = %bb.mainLoop
  br label %newFuncRoot
}

attributes #0 = { noreturn }

!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2, !3, !4}
!2 = !{!"OUT", i64 0, i64 0, i64 0, ptr null, i64 0}
!3 = !{!"OUT", i64 0, i64 0, i64 1, ptr @noDepsSyncBeginEnd.t1, i64 1}
!4 = !{!"IN", i64 0, i64 1, i64 0, ptr @noDepsSyncBeginEnd.t1, i64 2}
!5 = distinct !{!6, !7, !8}
!6 = !{!"OUT", i64 0, i64 0, i64 0, ptr null, i64 1}
!7 = !{!"IN", i64 0, i64 1, i64 0, ptr @noDepsSyncBeginEnd, i64 1}
!8 = !{!"OUT", i64 0, i64 0, i64 1, ptr @noDepsSyncBeginEnd, i64 2}
