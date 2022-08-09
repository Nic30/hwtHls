# Machine code for function t0_HlsSlicingTC_test_connection__HlsConnection: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.t0_HlsSlicingTC_test_connection__HlsConnection:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_HlsSlicingTC_test_connection__HlsConnection_whC:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s32) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s32) from %ir.a)
  GENFPGA_CSTORE %2:anyregcls(s32), %1:anyregcls, 0, 1 :: (volatile store (s32) into %ir.b, addrspace 1)
  G_BR %bb.1

# End machine code for function t0_HlsSlicingTC_test_connection__HlsConnection.

