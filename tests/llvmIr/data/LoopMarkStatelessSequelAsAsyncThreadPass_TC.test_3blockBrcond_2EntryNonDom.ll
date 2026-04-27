; ModuleID = 'test'
source_filename = "test"

define void @test_3blockBrcond_2EntryNonDom(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb.0:
  br label %bb.1

bb.1:                                             ; preds = %bb.1.t.0.slseqPExit, %bb.1.f.0.slseqPExit, %bb.0
  %acc = phi i8 [ 0, %bb.0 ], [ %v0, %bb.1.t.0.slseqPExit ], [ %v0, %bb.1.f.0.slseqPExit ]
  %slseq.EntryIdx = alloca i1, align 1
  store i1 poison, ptr %slseq.EntryIdx, align 1
  %v0 = load volatile i8, ptr addrspace(1) %i, align 1
  %c0 = icmp eq i8 %v0, 1
  br i1 %c0, label %bb.1.t.split, label %bb.1.f.split

bb.1.t.split:                                     ; preds = %bb.1
  store i1 true, ptr %slseq.EntryIdx, align 1
  br label %bb.1.t

bb.1.t:                                           ; preds = %bb.1.t.split
  %v0.t = load volatile i8, ptr addrspace(1) %i, align 1
  br label %bb.1.t.0

bb.1.t.0:                                         ; preds = %bb.1.t
  br label %bb.proxy

bb.1.f.split:                                     ; preds = %bb.1
  store i1 false, ptr %slseq.EntryIdx, align 1
  br label %bb.1.f

bb.1.f:                                           ; preds = %bb.1.f.split
  %v0.f = load volatile i8, ptr addrspace(1) %i, align 1
  br label %bb.1.f.0

bb.1.f.0:                                         ; preds = %bb.1.f
  br label %bb.proxy

bb.proxy:                                         ; preds = %bb.1.t.0, %bb.1.f.0
  %v0.t.reg2mem.0 = phi i8 [ %v0.t, %bb.1.t.0 ], [ poison, %bb.1.f.0 ]
  %v0.f.reg2mem.0 = phi i8 [ poison, %bb.1.t.0 ], [ %v0.f, %bb.1.f.0 ]
  %proxySrc = phi i1 [ false, %bb.1.f.0 ], [ true, %bb.1.t.0 ]
  call void @hwtHls.thread.split.begin.slsequel() #1, !hwtHls.thread.section !0
  %0 = load i1, ptr %slseq.EntryIdx, align 1
  switch i1 %0, label %bb.proxy.entry.def [
    i1 false, label %bb.1.f.slseq
    i1 true, label %bb.1.t.slseq
  ]

bb.proxy.split:                                   ; preds = %bb.1.t.0.slseq, %bb.1.f.0.slseq
  call void @hwtHls.thread.split.end.slsequel() #1, !hwtHls.thread.section !0
  switch i1 %proxySrc, label %bb.proxy.def [
    i1 false, label %bb.1.f.0.slseqPExit
    i1 true, label %bb.1.t.0.slseqPExit
  ]

bb.proxy.def:                                     ; preds = %bb.proxy.split
  unreachable

bb.1.f.0.slseqPExit:                              ; preds = %bb.proxy.split
  br label %bb.1

bb.1.t.0.slseqPExit:                              ; preds = %bb.proxy.split
  br label %bb.1

bb.1.f.slseq:                                     ; preds = %bb.proxy
  br label %bb.1.f.0.slseq

bb.1.f.0.slseq:                                   ; preds = %bb.1.f.slseq
  %v2 = add i8 %v0, %v0.f.reg2mem.0
  store volatile i8 %v2, ptr addrspace(2) %o, align 1
  br label %bb.proxy.split

bb.1.t.slseq:                                     ; preds = %bb.proxy
  br label %bb.1.t.0.slseq

bb.1.t.0.slseq:                                   ; preds = %bb.1.t.slseq
  %v1 = add i8 %v0.t.reg2mem.0, %acc
  store volatile i8 %v1, ptr addrspace(2) %o, align 1
  br label %bb.proxy.split

bb.proxy.entry.def:                               ; preds = %bb.proxy
  unreachable
}

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.thread.split.begin.slsequel() #0

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.thread.split.end.slsequel() #0

attributes #0 = { nofree nounwind willreturn }
attributes #1 = { memory(readwrite) }

!0 = distinct !{!"slsequel", i1 true, i1 false, i1 true, i1 true, i64 0, i64 0}
