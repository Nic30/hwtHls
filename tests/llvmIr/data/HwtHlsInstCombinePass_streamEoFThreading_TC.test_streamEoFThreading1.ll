define void @test_streamEoFThreading1(ptr addrspace(1) %o, ptr addrspace(2) %i) !hwtHls.streamIo !0 {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb2, %bb1, %bb0
  %.w0 = load volatile i37, ptr addrspace(2) %i, align 8
  %eof = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %.w0, i7 36) #2
  %0 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %.w0, i7 33) #2
  %1 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %.w0, i7 32) #2
  %2 = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %.w0, i7 32) #2
  %prevMaskBit1Impl8 = icmp ule i1 %0, %1
  call void @llvm.assume(i1 %prevMaskBit1Impl8)
  %3 = icmp eq i4 %2, -1
  %maskAll1IfNonLastImpl16 = or i1 %eof, %3
  call void @llvm.assume(i1 %maskAll1IfNonLastImpl16)
  %4 = xor i1 %0, true
  %.specExit = and i1 %eof, %4
  store volatile i1 %.specExit, ptr addrspace(1) %o, align 4
  br i1 %eof, label %bb2, label %bb1

bb2:                                              ; preds = %bb1
  store volatile i8 10, ptr addrspace(1) %o, align 4
  br label %bb1
}
