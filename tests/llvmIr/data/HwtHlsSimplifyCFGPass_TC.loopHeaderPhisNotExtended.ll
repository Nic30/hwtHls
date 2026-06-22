define void @loopHeaderPhisNotExtended(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %write) {
bb0:
  br label %bb.header

bb.header:                                        ; preds = %bb.header, %bb0
  %k3_key.0 = phi i16 [ undef, %bb0 ], [ %k3_key.1, %bb.header ]
  %k2_key.0 = phi i16 [ undef, %bb0 ], [ %k2_key.1, %bb.header ]
  %k1_key.0 = phi i16 [ undef, %bb0 ], [ %k1_key.1, %bb.header ]
  %k0_key.0 = phi i16 [ undef, %bb0 ], [ %k0_key.1, %bb.header ]
  %k0_vld.018 = phi i1 [ false, %bb0 ], [ %k0_vld.119, %bb.header ]
  %k1_vld.020 = phi i1 [ false, %bb0 ], [ %k1_vld.121, %bb.header ]
  %k2_vld.022 = phi i1 [ false, %bb0 ], [ %k2_vld.123, %bb.header ]
  %k3_vld.024 = phi i1 [ false, %bb0 ], [ %k3_vld.125, %bb.header ]
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
  %fewExitSw.sucSel.en.bb.header.bb.sw_c1 = icmp eq i2 %6, 1
  %fewExitSw.sucSel.en.bb.header.bb.sw_c2 = icmp eq i2 %6, -2
  %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd = icmp eq i2 %6, 0
  %7 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c2, i16 %k3_key.0, i16 %5
  %8 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c2, i16 %5, i16 %k2_key.0
  %9 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c2, i1 %4, i1 %k2_vld.022
  %10 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c2, i1 %k3_vld.024, i1 %4
  %11 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c1, i16 %k3_key.0, i16 %7
  %12 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c1, i16 %k2_key.0, i16 %8
  %13 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c1, i16 %5, i16 %k1_key.0
  %14 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c1, i1 %4, i1 %k1_vld.020
  %15 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c1, i1 %k2_vld.022, i1 %9
  %16 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_c1, i1 %k3_vld.024, i1 %10
  %k3_key.1 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd, i16 %k3_key.0, i16 %11
  %k2_key.1 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd, i16 %k2_key.0, i16 %12
  %k1_key.1 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd, i16 %k1_key.0, i16 %13
  %k0_key.1 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd, i16 %5, i16 %k0_key.0
  %k0_vld.119 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd, i1 %4, i1 %k0_vld.018
  %k1_vld.121 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd, i1 %k1_vld.020, i1 %14
  %k2_vld.123 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd, i1 %k2_vld.022, i1 %15
  %k3_vld.125 = select i1 %fewExitSw.sucSel.en.bb.header.bb.sw_setSwEnd, i1 %k3_vld.024, i1 %16
  br label %bb.header
}
