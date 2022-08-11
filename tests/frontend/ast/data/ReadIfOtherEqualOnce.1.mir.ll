# Machine code for function t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce:
  %2:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.a)
  %4:anyregcls(s1) = G_ICMP intpred(ne), %2:anyregcls(s8), i8 3
  %8:anyregcls(s1) = GENFPGA_NOT %4:anyregcls(s1)
  dead %5:anyregcls(s8) = GENFPGA_CLOAD %1:anyregcls, 0, %8:anyregcls(s1) :: (volatile load (s8) from %ir.b, addrspace 1)
  PseudoRET

# End machine code for function t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce.

