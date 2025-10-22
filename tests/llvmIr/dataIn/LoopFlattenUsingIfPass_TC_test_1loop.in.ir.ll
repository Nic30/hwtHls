; ModuleID = 'hwtHlsModule'
source_filename = "hwtHlsModule"
target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

define void @LoopFlattenUsingIfPass_ir_TC.test_1loop(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !prof !0 !hwtHls.io !1 {
bb0:
  br label %bb.pktLoop.head

bb.pktLoop.head:                                  ; preds = %bb0, %txConsumePendingOnLast
  %rx_read6.r0 = load volatile i133, ptr addrspace(1) %rx, align 32
  %rx_read6.r0.eof = call i1 @hwtHls.bitRangeGet.i133.i9.i1.128(i133 %rx_read6.r0, i9 128) #4
  %rx_read6.r0.empty = call i4 @hwtHls.bitRangeGet.i133.i9.i4.129(i133 %rx_read6.r0, i9 129) #4
  %0 = icmp eq i4 %rx_read6.r0.empty, 0
  %NonEoFImplEmptyEq0 = or i1 %rx_read6.r0.eof, %0
  call void @llvm.assume(i1 %NonEoFImplEmptyEq0)
  %rx_read6.r1 = load volatile i133, ptr addrspace(1) %rx, align 32
  %rx_read6.r1.data = call i128 @hwtHls.bitRangeGet.i133.i9.i128.0(i133 %rx_read6.r1, i9 0) #4
  %rx_read6.r1.eof = call i1 @hwtHls.bitRangeGet.i133.i9.i1.128(i133 %rx_read6.r1, i9 128) #4
  %rx_read6.r1.empty = call i4 @hwtHls.bitRangeGet.i133.i9.i4.129(i133 %rx_read6.r1, i9 129) #4
  %1 = icmp eq i4 %rx_read6.r1.empty, 0
  %NonEoFImplEmptyEq013 = or i1 %rx_read6.r1.eof, %1
  call void @llvm.assume(i1 %NonEoFImplEmptyEq013)
  br label %bb.forwardUntilEoF.axi4ss.head

bb.forwardUntilEoF.axi4ss.head:                   ; preds = %bb.forwardUntilEoF.axi4ss.head.latch, %bb.pktLoop.head
  %txData.0 = phi i128 [ undef, %bb.pktLoop.head ], [ %12, %bb.forwardUntilEoF.axi4ss.head.latch ]
  %rxDataEoF.0 = phi i1 [ %rx_read6.r1.eof, %bb.pktLoop.head ], [ %rx_read5.r1.eof, %bb.forwardUntilEoF.axi4ss.head.latch ]
  %rxData.0 = phi i128 [ %rx_read6.r1.data, %bb.pktLoop.head ], [ %rx_read5.r1.data, %bb.forwardUntilEoF.axi4ss.head.latch ]
  %2 = call i112 @hwtHls.bitRangeGet.i128.i8.i112.16(i128 %rxData.0, i8 16) #4
  %3 = call i16 @hwtHls.bitRangeGet.i128.i8.i16.16(i128 %rxData.0, i8 16) #4
  %4 = call i112 @hwtHls.bitRangeGet.i128.i8.i112.0(i128 %txData.0, i8 0) #4
  %rx_read5.r1 = load volatile i133, ptr addrspace(1) %rx, align 32
  %rx_read5.r1.data = call i128 @hwtHls.bitRangeGet.i133.i9.i128.0(i133 %rx_read5.r1, i9 0) #4
  %5 = call i16 @hwtHls.bitRangeGet.i133.i9.i16.0(i133 %rx_read5.r1, i9 0) #4
  %rx_read5.r1.eof = call i1 @hwtHls.bitRangeGet.i133.i9.i1.128(i133 %rx_read5.r1, i9 128) #4
  %rx_read5.r1.empty = call i4 @hwtHls.bitRangeGet.i133.i9.i4.129(i133 %rx_read5.r1, i9 129) #4
  %6 = icmp eq i4 %rx_read5.r1.empty, 0
  %NonEoFImplEmptyEq016 = or i1 %rx_read5.r1.eof, %6
  call void @llvm.assume(i1 %NonEoFImplEmptyEq016)
  %7 = icmp ugt i4 %rx_read5.r1.empty, -3
  %8 = and i1 %rx_read5.r1.eof, %7
  %9 = or i1 %rxDataEoF.0, %8
  %"(rx_read5)" = call i133 @hwtHls.bitConcat.i112.i16.i1.i4(i112 %2, i16 %5, i1 %9, i4 0) #4
  %10 = call i112 @hwtHls.bitRangeGet.i133.i9.i112.16(i133 %"(rx_read5)", i9 16) #4
  %11 = call i134 @hwtHls.bitConcat.i112.i16.i6(i112 %4, i16 %3, i6 24) #4
  store volatile i134 %11, ptr addrspace(2) %tx, align 32
  %12 = call i128 @hwtHls.bitConcat.i112.i16(i112 %10, i16 undef) #4
  br i1 %9, label %txConsumePendingOnLast, label %bb.forwardUntilEoF.axi4ss.head.latch

bb.forwardUntilEoF.axi4ss.head.latch:             ; preds = %bb.forwardUntilEoF.axi4ss.head
  br label %bb.forwardUntilEoF.axi4ss.head

txConsumePendingOnLast:                           ; preds = %bb.forwardUntilEoF.axi4ss.head
  %.lcssa = phi i112 [ %10, %bb.forwardUntilEoF.axi4ss.head ]
  %13 = call i134 @hwtHls.bitConcat.i112.i16.i6(i112 %.lcssa, i16 undef, i6 29) #4
  store volatile i134 %13, ptr addrspace(2) %tx, align 32
  br label %bb.pktLoop.head, !llvm.loop !6
}

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamReadStartOfFrame.p1(ptr addrspace(1) %ioArgPtr) #0

; Function Attrs: nofree nounwind willreturn
declare i150 @hwtHls.streamRead.p1.i64.i150(ptr addrspace(1) %isReliable, i64 %0, i1 %1) #0

; Function Attrs: nofree nounwind speculatable willreturn
declare i48 @hwtHls.bitRangeGet.i150.i9.i48.0(i150 %0, i9 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i48 @hwtHls.bitRangeGet.i150.i9.i48.48(i150 %0, i9 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i16 @hwtHls.bitRangeGet.i150.i9.i16.96(i150 %0, i9 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i16 @hwtHls.bitRangeGet.i150.i9.i16.112(i150 %0, i9 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i16 @hwtHls.bitRangeGet.i150.i9.i16.128(i150 %0, i9 %1) #1

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %ioArgPtr) #0

; Function Attrs: nofree nounwind speculatable willreturn
declare i96 @hwtHls.bitConcat.i48.i48(i48 %0, i48 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i112 @hwtHls.bitConcat.i96.i16(i96 %0, i16 %1) #1

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamWrite.p2.i112.i1.i1(ptr addrspace(2) %isEoF, i112 %0, i1 %1, i1 %2) #0

; Function Attrs: nofree nounwind willreturn
declare i133 @hwtHls.streamRead.p1.i64.i133(ptr addrspace(1) %isReliable, i64 %0, i1 %1) #0

; Function Attrs: nofree nounwind speculatable willreturn
declare i128 @hwtHls.bitRangeGet.i133.i9.i128.0(i133 %0, i9 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i4 @hwtHls.bitRangeGet.i133.i9.i4.129(i133 %0, i9 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i1 @hwtHls.bitRangeGet.i133.i9.i1.128(i133 %0, i9 %1) #1

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamWrite.masked.p2.i128.i4.i1.i1(ptr addrspace(2) %isEoF, i128 %0, i4 %1, i1 %2, i1 %3) #0

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %ioArgPtr) #0

; Function Attrs: nofree nounwind willreturn
declare void @hwtHls.streamReadEndOfFrame.p1(ptr addrspace(1) %ioArgPtr) #0

; Function Attrs: nocallback nofree nosync nounwind willreturn memory(inaccessiblemem: write)
declare void @llvm.assume(i1 noundef %0) #2

; Function Attrs: nofree nounwind speculatable willreturn
declare i16 @hwtHls.bitRangeGet.i133.i9.i16.0(i133 %0, i9 %1) #1

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare i4 @llvm.umin.i4(i4 %0, i4 %1) #3

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare i4 @llvm.umax.i4(i4 %0, i4 %1) #3

; Function Attrs: nofree nounwind speculatable willreturn
declare i144 @hwtHls.bitConcat.i128.i16(i128 %0, i16 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i150 @hwtHls.bitConcat.i144.i1.i5(i144 %0, i1 %1, i5 %2) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i112 @hwtHls.bitRangeGet.i128.i8.i112.16(i128 %0, i8 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i128 @hwtHls.bitConcat.i112.i16(i112 %0, i16 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i133 @hwtHls.bitConcat.i128.i1.i4(i128 %0, i1 %1, i4 %2) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i133 @hwtHls.bitConcat.i112.i16.i1.i4(i112 %0, i16 %1, i1 %2, i4 %3) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i16 @hwtHls.bitRangeGet.i128.i8.i16.16(i128 %0, i8 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i112 @hwtHls.bitRangeGet.i128.i8.i112.0(i128 %0, i8 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i134 @hwtHls.bitConcat.i128.i1.i5(i128 %0, i1 %1, i5 %2) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i112 @hwtHls.bitRangeGet.i133.i9.i112.16(i133 %0, i9 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i134 @hwtHls.bitConcat.i128.i6(i128 %0, i6 %1) #1

; Function Attrs: nofree nounwind speculatable willreturn
declare i134 @hwtHls.bitConcat.i112.i16.i6(i112 %0, i16 %1, i6 %2) #1

attributes #0 = { nofree nounwind willreturn }
attributes #1 = { nofree nounwind speculatable willreturn }
attributes #2 = { nocallback nofree nosync nounwind willreturn memory(inaccessiblemem: write) }
attributes #3 = { nocallback nofree nosync nounwind speculatable willreturn memory(none) }
attributes #4 = { memory(none) }

!0 = !{!"function_entry_count", i64 1}
!1 = distinct !{!1, !2}
!2 = !{!3, !5}
!3 = !{!"IN", i64 0, i64 133, i64 0, i1 true, ptr null, i64 0, ptr null, ptr null, !4, ptr null}
!4 = !{i32 128, i32 8, !"enable+empty", i32 0, !"eof", i32 0, i32 1}
!5 = !{!"OUT", i64 0, i64 133, i64 133, i1 true, ptr null, i64 1, ptr null, ptr null, !4, ptr null}
!6 = distinct !{!6, !7}
!7 = !{!"hwthls.loop.streamsegmentunroll.io", i32 0}