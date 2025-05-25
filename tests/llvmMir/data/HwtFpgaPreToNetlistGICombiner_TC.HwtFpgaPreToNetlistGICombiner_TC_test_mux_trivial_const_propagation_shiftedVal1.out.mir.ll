# Machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_shiftedVal1: IsSSA, NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_shiftedVal1:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 8, 1 :: (volatile load (s8) from %ir.dataIn, addrspace 1)
  %3:anyregcls = HWTFPGA_EXTRACT %2:anyregcls, 8, 0, 6
  %4:anyregcls = HWTFPGA_MERGE_VALUES i2 0, %3:anyregcls, 2, 6
  HWTFPGA_CSTORE %4:anyregcls, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.dataOut, addrspace 2)
  HWTFPGA_BR %bb.1

# End machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_shiftedVal1.

