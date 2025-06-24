define void @PhiToSelect0(ptr addrspace(1) %rx, ptr addrspace(2) %tx) {
bb0:
  br label %loop.pkt

loop.pkt:                                         ; preds = %loop.pkt.end, %bb0
  br label %loop.pkt.read

loop.pkt.read:                                    ; preds = %loop.pkt.end, %loop.pkt
  %curLen.015 = phi i5 [ 0, %loop.pkt ], [ %curLen.116, %loop.pkt.end ]
  %rx_read1.w0 = load volatile i10, ptr addrspace(1) %rx, align 2
  %0 = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read1.w0, i5 0) #1
  %1 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read1.w0, i5 9) #1
  %sig_.not = icmp eq i5 %curLen.015, 10
  %sig_8 = add i5 %curLen.015, 1
  %sig_6 = icmp eq i5 %curLen.015, 9
  %sig_7 = or i1 %1, %sig_6
  %2 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %0, i1 true, i1 %sig_7) #1
  br i1 %sig_.not, label %loop.pkt.end, label %bb0.enabled

bb0.enabled:                                      ; preds = %loop.pkt.read
  store volatile i10 %2, ptr addrspace(2) %tx, align 2
  br label %loop.pkt.end

loop.pkt.end:                                     ; preds = %bb0.enabled, %loop.pkt.read
  %curLen.116 = phi i5 [ %sig_8, %bb0.enabled ], [ %curLen.015, %loop.pkt.read ]
  br i1 %1, label %loop.pkt, label %loop.pkt.read
}
