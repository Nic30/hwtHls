# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=1, align=1, at location [SP+2]
  fi#1: size=1, align=1, at location [SP+2]
  fi#2: size=1, align=1, at location [SP+2]

bb.0.mainThread:
  %2:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.i, addrspace 1)
  %4:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s8), i8 10
  %6:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s8), i8 2
  %7:anyregcls(s2) = GENFPGA_MERGE_VALUES %4:anyregcls(s1), i1 true, 1, 1
  %10:anyregcls(s2) = GENFPGA_MUX i2 1, %6:anyregcls(s1), %7:anyregcls(s2)
  %12:anyregcls(s1) = GENFPGA_EXTRACT %10:anyregcls(s2), 0, 1
  %15:anyregcls(s8) = GENFPGA_MERGE_VALUES %12:anyregcls(s1), i2 1, %12:anyregcls(s1), i4 0, 1, 2, 1, 4
  GENFPGA_CSTORE %15:anyregcls(s8), %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  PseudoRET

# End machine code for function mainThread.

