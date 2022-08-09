# Machine code for function t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_whC:
; predecessors: %bb.0, %bb.2
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  %8:anyregcls(s8) = GENFPGA_MUX i8 10

bb.2.t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_wh:
; predecessors: %bb.1, %bb.2
  successors: %bb.1(0x04000000), %bb.2(0x7c000000); %bb.1(3.12%), %bb.2(96.88%)

  %3:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.dataIn)
  %4:anyregcls(s8) = G_SUB %8:anyregcls, %3:anyregcls
  GENFPGA_CSTORE %4:anyregcls(s8), %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.dataOut, addrspace 1)
  %6:anyregcls(s1) = G_ICMP intpred(eq), %4:anyregcls(s8), i8 0
  %8:anyregcls(s8) = GENFPGA_MUX %4:anyregcls(s8)
  %9:anyregcls(s1) = GENFPGA_NOT %6:anyregcls(s1)
  G_BRCOND %9:anyregcls(s1), %bb.2
  G_BR %bb.1

# End machine code for function t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2.

