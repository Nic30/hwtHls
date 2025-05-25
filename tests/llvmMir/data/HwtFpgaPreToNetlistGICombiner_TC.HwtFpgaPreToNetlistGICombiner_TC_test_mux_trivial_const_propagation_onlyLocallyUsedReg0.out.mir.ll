# Machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_onlyLocallyUsedReg0: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_onlyLocallyUsedReg0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %2:anyregcls(s8) = HWTFPGA_MUX i8 0

bb.1.bb1:
; predecessors: %bb.0, %bb.1, %bb.2
  successors: %bb.1(0x40000000), %bb.2(0x40000000); %bb.1(50.00%), %bb.2(50.00%)

  %3:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2:anyregcls(s8), i8 0
  HWTFPGA_BRCOND %3:anyregcls(s1), %bb.1

bb.2.bb2:
; predecessors: %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s8) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 8 :: (volatile load (s8) from %ir.dataIn, addrspace 1)
  HWTFPGA_BR %bb.1

# End machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_onlyLocallyUsedReg0.

