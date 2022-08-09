# Machine code for function t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=1, align=1, at location [SP+2]

bb.0.t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_whC:
; predecessors: %bb.0, %bb.2
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  %12:anyregcls(s8) = GENFPGA_MUX i8 10

bb.2.t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_IfC:
; predecessors: %bb.1, %bb.2
  successors: %bb.1(0x04000000), %bb.2(0x7c000000); %bb.1(3.12%), %bb.2(96.88%)

  %3:anyregcls(s1) = G_ICMP intpred(ult), %12:anyregcls(s8), i8 3
  %4:anyregcls(s8) = GENFPGA_MERGE_VALUES i1 true, %3:anyregcls(s1), i6 -1, 1, 1, 6
  %8:anyregcls(s8) = G_ADD %4:anyregcls, %12:anyregcls
  GENFPGA_CSTORE %8:anyregcls(s8), %0:anyregcls, 0, 1 :: (volatile store (s8) into %ir.dataOut)
  %10:anyregcls(s1) = G_ICMP intpred(eq), %8:anyregcls(s8), i8 0
  %12:anyregcls(s8) = GENFPGA_MUX %8:anyregcls(s8)
  %13:anyregcls(s1) = GENFPGA_NOT %10:anyregcls(s1)
  G_BRCOND %13:anyregcls(s1), %bb.2
  G_BR %bb.1

# End machine code for function t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0.

