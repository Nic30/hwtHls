define void @test_noSuboptimalLoopUnswitch(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
bb0:
  br label %mainLoop.split

mainLoop.split:                                   ; preds = %mainLoop.split, %copyLoop, %bb0
  %r0 = load volatile i17, ptr addrspace(1) %dataIn, align 4
  %r0.last = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %r0, i6 16) #1
  %0 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %r0, i6 0) #1
  %r1 = zext i8 %0 to i9
  %r1.last = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %r1, i5 8) #1
  %1 = call i17 @hwtHls.bitConcat.i8.i8.i1(i8 %0, i8 undef, i1 true) #1
  %2 = select i1 %r1.last, i17 %1, i17 %r0
  store volatile i17 %2, ptr addrspace(2) %dataOut, align 4
  %merge = or i1 %r0.last, %r1.last
  br i1 %merge, label %mainLoop.split, label %copyLoop

copyLoop:                                         ; preds = %mainLoop.split, %copyLoop
  %r2 = load volatile i17, ptr addrspace(1) %dataIn, align 4
  %r2.last = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %r2, i6 16) #1
  %3 = call i8 @hwtHls.bitRangeGet.i17.i6.i8.0(i17 %r2, i6 0) #1
  %r3 = zext i8 %3 to i9
  %r3.last = call i1 @hwtHls.bitRangeGet.i9.i5.i1.8(i9 %r3, i5 8) #1
  %4 = call i17 @hwtHls.bitConcat.i8.i8.i1(i8 %3, i8 undef, i1 true) #1
  %5 = select i1 %r3.last, i17 %4, i17 %r2
  store volatile i17 %5, ptr addrspace(2) %dataOut, align 4
  %merge2 = or i1 %r2.last, %r3.last
  br i1 %merge2, label %mainLoop.split, label %copyLoop
}
