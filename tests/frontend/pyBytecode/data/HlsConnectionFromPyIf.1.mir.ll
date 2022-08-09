# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x40000000), %bb.2(0x40000000); %bb.1(50.00%), %bb.2(50.00%)

  %2:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.i)
  %4:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s8), i8 2
  %8:anyregcls(s1) = GENFPGA_NOT %4:anyregcls(s1)
  G_BRCOND %8:anyregcls(s1), %bb.2

bb.1.block22:
; predecessors: %bb.0
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  GENFPGA_CSTORE i8 3, %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 1)

bb.2.common.ret:
; predecessors: %bb.0, %bb.1

  PseudoRET

# End machine code for function mainThread.

