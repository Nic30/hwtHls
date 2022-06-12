# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=1, align=1, at location [SP+2]

bb.0.mainThread:
  %2:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls(s1), 1 :: (volatile load (s8) from %ir.i)
  %4:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s8), i8 2
  %6:anyregcls(s1) = G_XOR %4:anyregcls, i1 true
  %7:anyregcls(s8) = GENFPGA_MERGE_VALUES i4 0, %6:anyregcls(s1), i2 1, %4:anyregcls(s1), 4, 1, 2, 1
  GENFPGA_CSTORE %7:anyregcls(s8), %1:anyregcls(s1), 1 :: (volatile store (s8) into %ir.o)
  PseudoRET

# End machine code for function mainThread.

