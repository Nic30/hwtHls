# Machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_onlyLocallyUsedReg1: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_onlyLocallyUsedReg1:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %6:anyregcls = HWTFPGA_MUX i8 0

bb.1.WhileSendSequence1.mainLoop:
; predecessors: %bb.0, %bb.3
  successors: %bb.3(0x40000000), %bb.2(0x40000000); %bb.3(50.00%), %bb.2(50.00%)

  %3:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %6:anyregcls, i8 0
  %7:anyregcls = HWTFPGA_MUX killed %6:anyregcls
  HWTFPGA_BRCOND killed %3:anyregcls(s1), %bb.3

bb.2.WhileSendSequence1.whileSize:
; predecessors: %bb.1, %bb.2
  successors: %bb.2(0x40000000), %bb.3(0x40000000); %bb.2(50.00%), %bb.3(50.00%)

  HWTFPGA_CSTORE %7:anyregcls, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.dataOut, addrspace 2)
  %7:anyregcls = HWTFPGA_ADD killed %7:anyregcls, i8 -1
  %5:anyregcls = HWTFPGA_ICMP intpred(ne), %7:anyregcls, i8 0
  HWTFPGA_BRCOND killed %5:anyregcls, %bb.2

bb.3.WhileSendSequence1.read:
; predecessors: %bb.1, %bb.2
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %6:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 8, 1 :: (volatile load (s8) from %ir.dataIn, addrspace 1)
  HWTFPGA_BR %bb.1

# End machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_trivial_const_propagation_onlyLocallyUsedReg1.

