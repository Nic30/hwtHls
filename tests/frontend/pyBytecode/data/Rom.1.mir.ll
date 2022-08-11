# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL40i0_40:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s2) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s2) from %ir.i)
  %4:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s2), i2 -2
  %6:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s2), i2 0
  %8:anyregcls(s1) = G_ICMP intpred(ne), %2:anyregcls(s2), i2 1
  %16:anyregcls(s32) = GENFPGA_MUX i32 8, %8:anyregcls(s1), i32 2
  %17:anyregcls(s32) = GENFPGA_MUX i32 1, %6:anyregcls(s1), %16:anyregcls(s32)
  %9:anyregcls(s32) = GENFPGA_MUX i32 4, %4:anyregcls(s1), %17:anyregcls(s32)
  GENFPGA_CSTORE %9:anyregcls(s32), %1:anyregcls, 0, 1 :: (volatile store (s32) into %ir.o, addrspace 1)
  G_BR %bb.1

# End machine code for function mainThread.

