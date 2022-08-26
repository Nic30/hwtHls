# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=4, align=4, at location [SP+2]

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL40i0_40:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s2) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s2) from %ir.i, addrspace 1)
  %4:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s2), i2 -2
  %6:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s2), i2 0
  %8:anyregcls(s1) = G_ICMP intpred(ne), %2:anyregcls(s2), i2 1
  %9:anyregcls(s4) = GENFPGA_MUX i4 4, %4:anyregcls(s1), i4 1, %6:anyregcls(s1), i4 -8, %8:anyregcls(s1), i4 2
  %10:anyregcls(s32) = GENFPGA_MERGE_VALUES %9:anyregcls(s4), i28 0, 4, 28
  GENFPGA_CSTORE %10:anyregcls(s32), %1:anyregcls, 0, 1 :: (volatile store (s32) into %ir.o, addrspace 2)
  G_BR %bb.1

# End machine code for function mainThread.

