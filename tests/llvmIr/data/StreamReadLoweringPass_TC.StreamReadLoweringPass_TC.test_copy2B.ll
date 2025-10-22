define void @StreamReadLoweringPass_TC.test_copy2B(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !hwtHls.param_addr_width !0 !hwtHls.streamIo !2 {
bb0:
  br label %bb.rx.sof

bb.rx.sof:                                        ; preds = %bb.eof, %bb0
  call void @hwtHls.streamReadStartOfFrame.p1(ptr addrspace(1) %rx) #2
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #2
  br label %bb.rx.read

bb.rx.read:                                       ; preds = %bb.rx.eofCheck, %bb.rx.sof
  %rx_read1 = call i10 @hwtHls.streamRead.p1.i64.i10(ptr addrspace(1) %rx, i64 8, i1 false) #2
  %rx_read_last4 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read1, i5 9) #3
  %rx_read_data = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read1, i5 0) #3
  %rx_read_strb = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %rx_read1, i5 8) #3
  br i1 %rx_read_strb, label %bb.tx.write, label %bb.rx.eofCheck

bb.tx.write:                                      ; preds = %bb.rx.read
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %rx_read_data, i1 %rx_read_last4) #2
  br label %bb.rx.eofCheck

bb.rx.eofCheck:                                   ; preds = %bb.tx.write, %bb.rx.read
  br i1 %rx_read_last4, label %bb.eof, label %bb.rx.read

bb.eof:                                           ; preds = %bb.rx.eofCheck
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #2
  call void @hwtHls.streamReadEndOfFrame.p1(ptr addrspace(1) %rx) #2
  br label %bb.rx.sof
}
