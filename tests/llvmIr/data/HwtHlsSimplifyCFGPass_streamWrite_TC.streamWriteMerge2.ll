define void @streamWriteMerge2(ptr addrspace(1) %maskIn, ptr addrspace(2) %tx) !hwtHls.io !0 {
bb0:
  br label %bb.pktLoop

bb.pktLoop:                                       ; preds = %bb.pktLoop, %bb0
  %m0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
  %m1.0 = load volatile i1, ptr addrspace(1) %maskIn, align 1
  %m1 = and i1 %m0, %m1.0
  %eof = load volatile i1, ptr addrspace(1) %maskIn, align 1
  %0 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %m1) #2
  call void @hwtHls.streamWrite.masked.p2.i16.i2.i1.i1.p0(ptr addrspace(2) %tx, i16 513, i2 %0, i1 false, i1 %eof, ptr null) #3
  br label %bb.pktLoop
}
