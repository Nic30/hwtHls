# Machine code for function t0_HlsSlicingTC_test_slice__HlsSlice: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=2, align=2, at location [SP+2]

bb.0.t0_HlsSlicingTC_test_slice__HlsSlice:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_HlsSlicingTC_test_slice__HlsSlice_whC:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s32) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s32) from %ir.a)
  %3:anyregcls(s16) = GENFPGA_EXTRACT %2:anyregcls(s32), 0, 16
  GENFPGA_CSTORE %3:anyregcls(s16), %1:anyregcls, 0, 1 :: (volatile store (s16) into %ir.b, addrspace 1)
  G_BR %bb.1

# End machine code for function t0_HlsSlicingTC_test_slice__HlsSlice.

