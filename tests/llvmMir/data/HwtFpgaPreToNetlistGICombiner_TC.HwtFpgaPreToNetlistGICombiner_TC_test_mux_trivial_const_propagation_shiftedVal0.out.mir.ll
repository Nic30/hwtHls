# Machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_shiftedVal0: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_shiftedVal0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls = HWTFPGA_ARG_GET 2

bb.1:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 8, 1 :: (volatile load (s8) from %ir.dataIn, addrspace 1)
  %3:anyregcls = HWTFPGA_CLOAD %1:anyregcls, 0, 3, 1 :: (volatile load (s8) from %ir.shIn, addrspace 1)
  %4:anyregcls = HWTFPGA_ICMP intpred(eq), %3:anyregcls, i3 2
  %5:anyregcls = HWTFPGA_EXTRACT %2:anyregcls, 8, 0, 6
  %7:anyregcls = HWTFPGA_EXTRACT %2:anyregcls, 8, 0, 5
  %11:anyregcls(s6) = HWTFPGA_MERGE_VALUES i1 false, %7:anyregcls, 1, 5
  %12:anyregcls = HWTFPGA_MUX %5:anyregcls, %4:anyregcls, %11:anyregcls(s6)
  %13:anyregcls = HWTFPGA_EXTRACT %12:anyregcls, 6, 0, 6
  %14:anyregcls = HWTFPGA_MERGE_VALUES i2 0, %13:anyregcls, 2, 6
  HWTFPGA_CSTORE %14:anyregcls, %2:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.dataOut, addrspace 2)
  HWTFPGA_BR %bb.1

# End machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_shiftedVal0.

