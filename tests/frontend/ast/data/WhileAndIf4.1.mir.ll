# Machine code for function t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %12:anyregcls(s8) = GENFPGA_MUX i8 10

bb.1.t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_whC:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %3:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.dataIn)
  %4:anyregcls(s8) = G_SUB %12:anyregcls, %3:anyregcls
  %6:anyregcls(s1) = G_ICMP intpred(uge), %4:anyregcls(s8), i8 5
  %10:anyregcls(s1) = GENFPGA_NOT %6:anyregcls(s1)
  GENFPGA_CSTORE %4:anyregcls(s8), %1:anyregcls, 0, %10:anyregcls(s1) :: (volatile store (s8) into %ir.dataOut, addrspace 1)
  %12:anyregcls(s8) = GENFPGA_MUX %4:anyregcls(s8)
  G_BR %bb.1

# End machine code for function t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4.

