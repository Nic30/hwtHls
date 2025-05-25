define void @test_streamEoFThreading2(ptr addrspace(1) %o, ptr addrspace(2) %i) !hwtHls.streamIo !0 {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb0
  br label %bb2

bb2:                                              ; preds = %bb6.eof, %bb1
  br label %bb3

bb3:                                              ; preds = %bb5.exit, %bb2
  %r = load volatile i19, ptr addrspace(2) %i, align 4
  %0 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.17(i19 %r, i6 17) #1
  %r.eof = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %r, i6 18) #1
  %r.m0 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %r, i6 16) #1
  %r.m1 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %r, i6 17) #1
  %1 = xor i1 %r.eof, true
  %r.m0.specExit = or i1 %1, %r.m0
  %2 = xor i1 %r.m1, true
  %.1 = and i1 %r.m0, %2
  %3 = icmp ne i2 %0, -2
  %.specExit = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %3) #1
  %4 = or i1 %.1, %r.m1
  %.specExit4 = and i1 %r.eof, %4
  br i1 %r.m0.specExit, label %bb4.write, label %bb5.exit

bb4.write:                                        ; preds = %bb3
  store volatile i2 %.specExit, ptr addrspace(1) %o, align 4
  store volatile i1 %.specExit4, ptr addrspace(1) %o, align 4
  br label %bb5.exit

bb5.exit:                                         ; preds = %bb4.write, %bb3
  br i1 %r.eof, label %bb6.eof, label %bb3

bb6.eof:                                          ; preds = %bb5.exit
  br label %bb2
}
