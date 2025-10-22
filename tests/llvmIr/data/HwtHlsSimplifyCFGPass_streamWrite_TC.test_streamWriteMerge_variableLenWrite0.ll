define void @test_streamWriteMerge_variableLenWrite0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !hwtHls.io !0 {
bb0:
  br label %mainLoop

mainLoop:                                         ; preds = %bb.ret, %bb0
  call void @hwtHls.streamReadStartOfFrame.p1(ptr addrspace(1) %rx) #2
  %rx_read1 = call i10 @hwtHls.streamRead.p1.i64.i1.i10(ptr addrspace(1) %rx, i64 8, i1 true) #2
  %rx_read_strb = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %rx_read1, i5 8) #3
  %rx_read_data = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read1, i5 0) #3
  %rx_read_last = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read1, i5 9) #3
  call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #2
  call void @hwtHls.streamWrite.masked.p2.i8.i1.i1.i1.p0(ptr addrspace(2) %tx, i8 %rx_read_data, i1 %rx_read_strb, i1 false, i1 %rx_read_last, ptr null) #2
  br i1 %rx_read_last, label %bb.ret, label %copyLoop

copyLoop:                                         ; preds = %copyLoop, %mainLoop
  %rx_read7 = call i10 @hwtHls.streamRead.p1.i64.i1.i10(ptr addrspace(1) %rx, i64 8, i1 false) #2
  %rx_read_last9 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read7, i5 9) #3
  %rx_read_data8 = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read7, i5 0) #3
  %rx_read_strb12 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %rx_read7, i5 8) #3
  call void @hwtHls.streamWrite.masked.p2.i8.i1.i1.i1.p0(ptr addrspace(2) %tx, i8 %rx_read_data8, i1 %rx_read_strb12, i1 false, i1 %rx_read_last9, ptr null) #2
  br i1 %rx_read_last9, label %bb.ret, label %copyLoop

bb.ret:                                           ; preds = %copyLoop, %mainLoop
  call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #2
  call void @hwtHls.streamReadEndOfFrame.p1(ptr addrspace(1) %rx) #2
  br label %mainLoop
}
