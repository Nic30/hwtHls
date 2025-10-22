define void @test_streamEoFThreading2(ptr addrspace(1) %o, ptr addrspace(2) %i) !hwtHls.streamIo !0 {
bb0:
  br label %bb1

bb1:                                              ; preds = %bb0
  br label %bb2

bb2:                                              ; preds = %bb6.eof, %bb1
  br label %bb3

bb3:                                              ; preds = %bb5.exit, %bb2
  %r = load volatile i19, ptr addrspace(2) %i, align 4
  %r.eof = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %r, i6 18) #1
  %r.m0 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %r, i6 16) #1
  %r.m1 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %r, i6 17) #1
  %0 = xor i1 %r.m1, true
  %1 = and i1 %r.eof, %0
  %.1 = and i1 %r.m0, %1
  %.2 = and i1 %r.m1, %r.eof
  %2 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %r.m1) #1
  %3 = or i1 %.1, %.2
  %4 = sext i1 %3 to i2
  br i1 %r.m0, label %bb4.write, label %bb5.exit

bb4.write:                                        ; preds = %bb3
  store volatile i2 %2, ptr addrspace(1) %o, align 4
  store volatile i2 %4, ptr addrspace(1) %o, align 4
  br label %bb5.exit

bb5.exit:                                         ; preds = %bb4.write, %bb3
  br i1 %r.eof, label %bb6.eof, label %bb3

bb6.eof:                                          ; preds = %bb5.exit
  br label %bb2
}
