# Machine code for function t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=1, align=1, at location [SP+2]
  fi#1: size=1, align=1, at location [SP+2]

bb.0.t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1_whC:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.a)
  %3:anyregcls(s7) = GENFPGA_EXTRACT %2:anyregcls(s8), 0, 7
  %6:anyregcls(s8) = GENFPGA_MERGE_VALUES i1 false, %3:anyregcls(s7), 1, 7
  GENFPGA_CSTORE %6:anyregcls(s8), %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.b, addrspace 1)
  G_BR %bb.1

# End machine code for function t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1.

