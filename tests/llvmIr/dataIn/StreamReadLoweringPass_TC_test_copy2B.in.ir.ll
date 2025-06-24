; ModuleID = 'hwtHlsModule'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"


define void @StreamReadLoweringPass_TC.test_copy2B(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !hwtHls.param_addr_width !1 !hwtHls.streamIo !3 {
bb0:
  br label %bb.rx.sof

bb.rx.sof:                                    ; preds = %bb0, %bb.eof
  call void @hwtHls.streamReadStartOfFrame.p1(ptr addrspace(1) %rx) #2
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #2
  br label %bb.rx.read

bb.rx.read:                              ; preds = %bb.rx.eofCheck, %bb.rx.sof
  %rx_read1 = call i10 @hwtHls.streamRead.p1.i64.i10(ptr addrspace(1) %rx, i64 8, i1 false) #2
  %rx_read_last4 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read1, i5 9) #3
  %rx_read_data = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read1, i5 0) #3
  %rx_read_strb = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %rx_read1, i5 8) #3
  br i1 %rx_read_strb, label %bb.tx.write, label %bb.rx.eofCheck

bb.tx.write:                             ; preds = %bb.rx.read
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %rx_read_data, i1 %rx_read_last4) #2
  br label %bb.rx.eofCheck

bb.rx.eofCheck:                             ; preds = %bb.rx.read, %bb.tx.write
  br i1 %rx_read_last4, label %bb.eof, label %bb.rx.read

bb.eof:                                   ; preds = %bb.rx.eofCheck
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #2
  call void @hwtHls.streamReadEndOfFrame.p1(ptr addrspace(1) %rx) #2
  br label %bb.rx.sof
}

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamReadStartOfFrame.p1(ptr addrspace(1) %ioArgPtr) #0

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %ioArgPtr) #0

; Function Attrs: nofree nounwind willreturn
declare i10 @hwtHls.streamRead.p1.i64.i10(ptr addrspace(1) %isReliable, i64 %0, i1 %1) #0

; Function Attrs: nofree nounwind speculatable willreturn
declare i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %0, i5 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %0, i5 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %0, i5 %1) #1

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %isEoF, i8 %0, i1 %1) #0

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %ioArgPtr) #0

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamReadEndOfFrame.p1(ptr addrspace(1) %ioArgPtr) #0

attributes #0 = { nofree nounwind willreturn }
attributes #1 = { nofree nounwind speculatable willreturn }
attributes #2 = { memory(argmem: readwrite) }
attributes #3 = { memory(none) }

!1 = distinct !{!1, !2}
!2 = !{i32 0, i32 0}
!3 = !{!4, !5}
!4 = !{i32 0, i32 0, i32 16, i32 8, !"mask", i32 0, !"eof", i32 0, i32 1}
!5 = !{i32 1, i32 1, i32 16, i32 8, !"mask", i32 0, !"eof", i32 0, i32 1}
