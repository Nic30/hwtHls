define void @test_selectSimplify0(ptr addrspace(1) %byte_cnt, ptr addrspace(2) %i) {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb1, %bb0
  %byte_cnt1.0 = phi i16 [ 0, %bb0 ], [ %3, %bb1 ]
  %i_read1 = call i19 @hwtHls.streamRead.p2.i64.i19(ptr addrspace(2) %i, i64 16) #2
  %0 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.16(i19 %i_read1, i6 16) #3
  %1 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %i_read1, i6 16) #3
  %brmerge = icmp ne i2 %0, -1
  %.mux = select i1 %1, i8 1, i8 0
  %iHw64 = trunc i8 %.mux to i2
  %iHw.zext = zext i2 %iHw64 to i8
  %wordByteCnt.0 = select i1 %brmerge, i8 %iHw.zext, i8 2
  %wordByteCnt81 = trunc i8 %wordByteCnt.0 to i2
  %2 = zext i2 %wordByteCnt81 to i16
  %3 = add i16 %byte_cnt1.0, %2
  store volatile i16 %3, ptr addrspace(1) %byte_cnt, align 2
  br label %bb1
}
