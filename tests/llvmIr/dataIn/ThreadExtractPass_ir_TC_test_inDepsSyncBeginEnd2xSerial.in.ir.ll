source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

declare void @hwtHls.thread.split.begin.t1() #0
declare void @hwtHls.thread.split.end.t1() #0
declare void @hwtHls.thread.split.begin.t2() #0
declare void @hwtHls.thread.split.end.t2() #0

define void @inDepsSyncBeginEnd2xSerial(ptr addrspace(1) %i0, ptr addrspace(2) %o0, ptr addrspace(3) %o1, ptr addrspace(4) %o2) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.mainLoop

bb.mainLoop:                                      ; preds = %bb0, %bb.mainLoop
  store volatile i8 0, ptr addrspace(2) %o0, align 1
  %i.v0 = load volatile i8, ptr addrspace(1) %i0
  %i.v1 = load volatile i8, ptr addrspace(1) %i0
  call void @hwtHls.thread.split.begin.t1() #1, !hwtHls.thread.section !6
  store volatile i8 %i.v0, ptr addrspace(3) %o1, align 1
  call void @hwtHls.thread.split.end.t1() #1, !hwtHls.thread.section !6
  call void @hwtHls.thread.split.begin.t2() #1, !hwtHls.thread.section !7
  store volatile i8 %i.v1, ptr addrspace(4) %o2, align 1
  call void @hwtHls.thread.split.end.t2() #1, !hwtHls.thread.section !7
  br label %bb.mainLoop
}


attributes #0 = { nofree nounwind willreturn }
attributes #1 = { noreturn }
attributes #2 = { nocallback nofree nosync nounwind willreturn memory(argmem: readwrite) }
!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!2, !3, !4, !5}
!2 = !{!"IN", i64 0, i64 8, i64 8, ptr null, i64 0}
!3 = !{!"OUT", i64 0, i64 8, i64 8, ptr null, i64 1}
!4 = !{!"OUT", i64 0, i64 8, i64 8, ptr null, i64 2}
!5 = !{!"OUT", i64 0, i64 8, i64 8, ptr null, i64 2}
!6 = distinct !{!"t1", i1 true, i1 false, i1 true, i1 false, i64 0, i64 0}
!7 = distinct !{!"t2", i1 true, i1 false, i1 true, i1 false, i64 0, i64 0}

