# Machine code for function t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce:
  successors: %bb.1(0x40000000), %bb.2(0x40000000); %bb.1(50.00%), %bb.2(50.00%)

  %2:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.a)
  %4:anyregcls(s1) = G_ICMP intpred(ne), %2:anyregcls(s8), i8 3
  G_BRCOND %4:anyregcls(s1), %bb.2

bb.1.t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_If:
; predecessors: %bb.0
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  dead %5:anyregcls(s8) = GENFPGA_CLOAD %1:anyregcls, 0, 1 :: (volatile load (s8) from %ir.b, addrspace 1)

bb.2.t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_IfE:
; predecessors: %bb.0, %bb.1

  PseudoRET

# End machine code for function t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce.

