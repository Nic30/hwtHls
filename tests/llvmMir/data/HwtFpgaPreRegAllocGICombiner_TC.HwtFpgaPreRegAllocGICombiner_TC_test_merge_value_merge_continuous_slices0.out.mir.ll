# Machine code for function HwtFpgaPreRegAllocGICombiner_TC_test_merge_value_merge_continuous_slices0: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.HwtFpgaPreRegAllocGICombiner_TC_test_merge_value_merge_continuous_slices0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.bb1:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s16) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
  %6:anyregcls(s4) = HWTFPGA_EXTRACT %2:anyregcls(s16), 16, 1, 4
  HWTFPGA_CSTORE %6:anyregcls(s4), %1:anyregcls, 0, 4, 1 :: (volatile store (s4) into %ir.o, addrspace 2)
  HWTFPGA_BR %bb.1

# End machine code for function HwtFpgaPreRegAllocGICombiner_TC_test_merge_value_merge_continuous_slices0.

