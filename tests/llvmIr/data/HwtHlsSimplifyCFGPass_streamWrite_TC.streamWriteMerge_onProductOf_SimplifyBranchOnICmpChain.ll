define void @streamWriteMerge_onProductOf_SimplifyBranchOnICmpChain(ptr addrspace(1) %rx, ptr addrspace(2) %tx) !hwtHls.io !0 {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %loop.pkt, %bb.write1, %bb0
  %wEn = load volatile i3, ptr addrspace(1) %rx, align 4
  call void @hwtHls.streamWrite.p2.i8.i1.i1.p0(ptr addrspace(2) %tx, i8 1, i1 false, i1 false, ptr null) #1
  %0 = icmp eq i3 %wEn, 0
  %1 = xor i1 %0, true
  %2 = icmp eq i3 %wEn, 2
  %3 = xor i1 %2, true
  %4 = and i1 %3, %1
  %5 = icmp eq i3 %wEn, 1
  %6 = xor i1 %5, true
  %7 = and i1 %6, %4
  br i1 %7, label %bb.write1, label %loop.pkt

bb.write1:                                        ; preds = %loop.pkt
  call void @hwtHls.streamWrite.p2.i8.i1.i1.p0(ptr addrspace(2) %tx, i8 2, i1 false, i1 true, ptr null) #1
  br label %loop.pkt
}
