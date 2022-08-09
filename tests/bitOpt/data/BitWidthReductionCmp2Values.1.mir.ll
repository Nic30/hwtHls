# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=1, align=1, at location [SP+2]
  fi#1: size=2, align=2, at location [SP+2]

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL10i0_10:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s16) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s16) from %ir.i)
  %4:anyregcls(s1) = G_ICMP intpred(ne), %2:anyregcls(s16), i16 11
  %5:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s16), i16 11
  %7:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s16), i16 10
  %8:anyregcls(s4) = GENFPGA_MERGE_VALUES %5:anyregcls(s1), %4:anyregcls(s1), i2 -2, 1, 1, 2
  %11:anyregcls(s4) = GENFPGA_MUX i4 4, %7:anyregcls(s1), %8:anyregcls(s4)
  %13:anyregcls(s16) = GENFPGA_MERGE_VALUES %11:anyregcls(s4), i12 1, 4, 12
  GENFPGA_CSTORE %13:anyregcls(s16), %1:anyregcls, 0, 1 :: (volatile store (s16) into %ir.o, addrspace 1)
  G_BR %bb.1

# End machine code for function mainThread.

