; ModuleID = 'test'
source_filename = "test"

define void @test_noBranch(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb.0:
  br label %bb.1

bb.1:                                             ; preds = %bb.1.slseqPExit, %bb.0
  %acc = phi i8 [ 0, %bb.0 ], [ %v0, %bb.1.slseqPExit ]
  %v0 = load volatile i8, ptr addrspace(1) %i, align 1
  br label %bb.proxy

bb.proxy:                                         ; preds = %bb.1
  %proxySrc = phi i1 [ false, %bb.1 ]
  call void @hwtHls.thread.split.begin.slsequel() #1, !hwtHls.thread.section !0
  br label %bb.1.slseq

bb.proxy.split:                                   ; preds = %bb.1.slseq
  call void @hwtHls.thread.split.end.slsequel() #1, !hwtHls.thread.section !0
  switch i1 %proxySrc, label %bb.proxy.def [
    i1 false, label %bb.1.slseqPExit
  ]

bb.proxy.def:                                     ; preds = %bb.proxy.split
  unreachable

bb.1.slseqPExit:                                  ; preds = %bb.proxy.split
  br label %bb.1

bb.1.slseq:                                       ; preds = %bb.proxy
  %v1 = add i8 %v0, %acc
  store volatile i8 %v1, ptr addrspace(2) %o, align 1
  br label %bb.proxy.split
}

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.thread.split.begin.slsequel() #0

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.thread.split.end.slsequel() #0

attributes #0 = { nofree nounwind willreturn }
attributes #1 = { memory(readwrite) }

!0 = distinct !{!"slsequel", i1 true, i1 false, i1 true, i1 true, i64 0, i64 0}
