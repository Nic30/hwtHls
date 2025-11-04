# Machine code for function HwtFpgaPreRegAllocGICombiner_TC_test_extract_on_merge_values0: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.HwtFpgaPreRegAllocGICombiner_TC_test_extract_on_merge_values0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.bb1:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s16) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
  %8:anyregcls(s8) = HWTFPGA_EXTRACT %2:anyregcls(s16), 16, 8, 8
  %3:anyregcls(s16) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
  %9:anyregcls(s8) = HWTFPGA_EXTRACT %3:anyregcls(s16), 16, 0, 8
  %4:anyregcls(s16) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
  HWTFPGA_CSTORE %2:anyregcls(s16), %1:anyregcls, 0, 16, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
  %7:anyregcls(s16) = HWTFPGA_MERGE_VALUES %8:anyregcls(s8), %9:anyregcls(s8), 8, 8
  HWTFPGA_CSTORE %7:anyregcls(s16), %1:anyregcls, 0, 16, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
  HWTFPGA_BR %bb.1

# End machine code for function HwtFpgaPreRegAllocGICombiner_TC_test_extract_on_merge_values0.

