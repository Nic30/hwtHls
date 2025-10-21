# Machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge_twoWritingSameReg2: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge_twoWritingSameReg2:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.bb1:
; predecessors: %bb.0
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  %2:anyregcls(s16) = HWTFPGA_IMPLICIT_DEF 16

bb.2.bb2:
; predecessors: %bb.1, %bb.2
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  %6:anyregcls(s16) = HWTFPGA_MUX i16 1
  %5:anyregcls(s16) = HWTFPGA_ADD %6:anyregcls(s16), i16 1
  HWTFPGA_CSTORE %5:anyregcls(s16), %1:anyregcls, 0, 16, 1 :: (volatile store (s16) into %ir.txBody, addrspace 2)
  %3:anyregcls(s16) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 16 :: (volatile load (s16) from %ir.rx, addrspace 1)
  %4:anyregcls(s1) = HWTFPGA_EXTRACT %3:anyregcls(s16), 16, 0, 1
  %2:anyregcls(s16) = HWTFPGA_MUX killed %6:anyregcls(s16), %4:anyregcls(s1), %3:anyregcls(s16)
  HWTFPGA_CSTORE %2:anyregcls(s16), %1:anyregcls, 0, 16, 1 :: (volatile store (s16) into %ir.txBody, addrspace 2)
  HWTFPGA_BR %bb.2

# End machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge_twoWritingSameReg2.

