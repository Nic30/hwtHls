define void @streamWriteMerge1(ptr addrspace(1) %maskIn, ptr addrspace(2) %tx) {
bb0:
  br label %bb.pktLoop

bb.pktLoop:                                       ; preds = %bb.writesExit, %bb0
  %m0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
  %m1.0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
  %m1 = and i1 %m0, %m1.0
  %eof = load volatile i1, ptr addrspace(1) %maskIn, align 1
  br i1 %m0, label %bb.w1, label %bb.writesExit

bb.w1:                                            ; preds = %bb.pktLoop
  %0 = call i2 @hwtHls.bitConcat.i1.i1(i1 %m0, i1 %m1) #3
  call void @hwtHls.streamWrite.masked.p2.i16.i2.i1(ptr addrspace(2) %tx, i16 513, i2 %0, i1 %eof) #4
  br label %bb.writesExit

bb.writesExit:                                    ; preds = %bb.w1, %bb.pktLoop
  br label %bb.pktLoop
}
