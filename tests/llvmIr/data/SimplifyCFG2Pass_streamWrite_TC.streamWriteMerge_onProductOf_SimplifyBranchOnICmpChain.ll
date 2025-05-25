define void @streamWriteMerge_onProductOf_SimplifyBranchOnICmpChain(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %loop.pkt.latch, %bb0
  %wEn = load volatile i3, ptr addrspace(1) %rx, align 4
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 1, i1 false) #1
  switch i3 %wEn, label %bb.write1 [
    i3 0, label %loop.pkt.latch
    i3 2, label %loop.pkt.latch
    i3 1, label %loop.pkt.latch
  ]

bb.write1:                                        ; preds = %loop.pkt
  call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 2, i1 true) #1
  br label %loop.pkt.latch

loop.pkt.latch:                                   ; preds = %loop.pkt, %loop.pkt, %loop.pkt, %bb.write1
  br label %loop.pkt
}
