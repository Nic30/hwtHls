define void @loopHeaderPhisNotExtended(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %write) {
bb0:
  br label %bb.header

bb.header:                                        ; preds = %bb.sw_setSwEnd, %bb0
  %k3_key.0 = phi i16 [ undef, %bb0 ], [ %k3_key.1, %bb.sw_setSwEnd ]
  %k2_key.0 = phi i16 [ undef, %bb0 ], [ %k2_key.1, %bb.sw_setSwEnd ]
  %k1_key.0 = phi i16 [ undef, %bb0 ], [ %k1_key.1, %bb.sw_setSwEnd ]
  %k0_key.0 = phi i16 [ undef, %bb0 ], [ %k0_key.1, %bb.sw_setSwEnd ]
  %k0_vld.018 = phi i1 [ false, %bb0 ], [ %k0_vld.119, %bb.sw_setSwEnd ]
  %k1_vld.020 = phi i1 [ false, %bb0 ], [ %k1_vld.121, %bb.sw_setSwEnd ]
  %k2_vld.022 = phi i1 [ false, %bb0 ], [ %k2_vld.123, %bb.sw_setSwEnd ]
  %k3_vld.024 = phi i1 [ false, %bb0 ], [ %k3_vld.125, %bb.sw_setSwEnd ]
  %0 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k0_key.0, i1 %k0_vld.018) #1
  store volatile i17 %0, ptr addrspace(1) %keyForMatchThread_0, align 4
  %1 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k1_key.0, i1 %k1_vld.020) #1
  store volatile i17 %1, ptr addrspace(2) %keyForMatchThread_1, align 4
  %2 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k2_key.0, i1 %k2_vld.022) #1
  store volatile i17 %2, ptr addrspace(3) %keyForMatchThread_2, align 4
  %3 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k3_key.0, i1 %k3_vld.024) #1
  store volatile i17 %3, ptr addrspace(4) %keyForMatchThread_3, align 4
  %write_read = load volatile i19, ptr addrspace(5) %write, align 4
  %4 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %write_read, i6 18) #1
  %5 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.2(i19 %write_read, i6 2) #1
  %6 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19 %write_read, i6 0) #1
  switch i2 %6, label %bb.header.unreachabledefault [
    i2 0, label %bb.sw_setSwEnd
    i2 1, label %bb.sw_c1
    i2 -2, label %bb.sw_c2
    i2 -1, label %bb.sw_c3
  ]

bb.header.unreachabledefault:                     ; preds = %bb.header
  unreachable

bb.sw_c1:                                         ; preds = %bb.header
  br label %bb.sw_setSwEnd

bb.sw_c2:                                         ; preds = %bb.header
  br label %bb.sw_setSwEnd

bb.sw_c3:                                         ; preds = %bb.header
  br label %bb.sw_setSwEnd

bb.sw_setSwEnd:                                   ; preds = %bb.sw_c3, %bb.sw_c2, %bb.sw_c1, %bb.header
  %k3_key.1 = phi i16 [ %5, %bb.sw_c3 ], [ %k3_key.0, %bb.sw_c2 ], [ %k3_key.0, %bb.sw_c1 ], [ %k3_key.0, %bb.header ]
  %k2_key.1 = phi i16 [ %k2_key.0, %bb.sw_c3 ], [ %5, %bb.sw_c2 ], [ %k2_key.0, %bb.sw_c1 ], [ %k2_key.0, %bb.header ]
  %k1_key.1 = phi i16 [ %k1_key.0, %bb.sw_c3 ], [ %k1_key.0, %bb.sw_c2 ], [ %5, %bb.sw_c1 ], [ %k1_key.0, %bb.header ]
  %k0_key.1 = phi i16 [ %k0_key.0, %bb.sw_c3 ], [ %k0_key.0, %bb.sw_c2 ], [ %k0_key.0, %bb.sw_c1 ], [ %5, %bb.header ]
  %k0_vld.119 = phi i1 [ %k0_vld.018, %bb.sw_c3 ], [ %k0_vld.018, %bb.sw_c2 ], [ %k0_vld.018, %bb.sw_c1 ], [ %4, %bb.header ]
  %k1_vld.121 = phi i1 [ %k1_vld.020, %bb.sw_c3 ], [ %k1_vld.020, %bb.sw_c2 ], [ %4, %bb.sw_c1 ], [ %k1_vld.020, %bb.header ]
  %k2_vld.123 = phi i1 [ %k2_vld.022, %bb.sw_c3 ], [ %4, %bb.sw_c2 ], [ %k2_vld.022, %bb.sw_c1 ], [ %k2_vld.022, %bb.header ]
  %k3_vld.125 = phi i1 [ %4, %bb.sw_c3 ], [ %k3_vld.024, %bb.sw_c2 ], [ %k3_vld.024, %bb.sw_c1 ], [ %k3_vld.024, %bb.header ]
  br label %bb.header
}
