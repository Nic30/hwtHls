; ModuleID = 'test'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @noDepsSyncNone(ptr addrspace(1) %dataOut0) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.mainLoop.threadSplit.begint1

bb.mainLoop.threadSplit.begint1:                  ; preds = %bb0, %bb.mainLoop.threadSplit.end.t1
  store volatile i8 0, ptr addrspace(1) %dataOut0, align 1
  br label %codeRepl

codeRepl:                                         ; preds = %bb.mainLoop.threadSplit.begint1
  br label %bb.mainLoop.threadSplit.end.t1

bb.mainLoop.threadSplit.end.t1:                   ; preds = %codeRepl
  br label %bb.mainLoop.threadSplit.begint1
}

; Function Attrs: noreturn
define internal void @noDepsSyncNone.t1(ptr addrspace(1) %dataOut1) #0 !hwtHls.io !3 {
threadEntry:
  br label %newFuncRoot

newFuncRoot:                                      ; preds = %bb.mainLoop.threadSplit.end.t1.exitStub, %threadEntry
  br label %bb.mainLoop

bb.mainLoop:                                      ; preds = %newFuncRoot
  store volatile i8 1, ptr addrspace(1) %dataOut1, align 1
  br label %bb.mainLoop.threadSplit.end.t1.exitStub

bb.mainLoop.threadSplit.end.t1.exitStub:          ; preds = %bb.mainLoop
  br label %newFuncRoot
}

attributes #0 = { noreturn }

!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2}
!2 = !{!"OUT", i64 0, i64 0, i64 0, ptr null, i64 0}
!3 = distinct !{!4}
!4 = !{!"OUT", i64 0, i64 0, i64 0, ptr null, i64 1}
