# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  %2:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.i)
  %4:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s8), i8 2
  GENFPGA_CSTORE i8 3, %1:anyregcls, 0, %4:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 1)
  PseudoRET

# End machine code for function mainThread.

